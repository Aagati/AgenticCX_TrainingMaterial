"""
Lab-2: Banking - Ship a Smarter Offer Engine Without Shipping a Bad One.

banking_traces.json is 13 historical personalization sends — a log of what
SOME engine already offered ten banking customers before this lab existed.
Six of those thirteen have a real problem: an ineligible product, a missing
disclosure, a banned phrase. Nobody caught them at the time, because nobody
was running continuous QA.

This lab builds that QA loop, and the ENGINE it protects, together:

  PersonalisationEngine   -- ranks/filters banking product offers per
                             customer (segment, credit band, balance, already
                             held, already declined).
  QA check registry        -- the same checks run in two very different
                             contexts: MINING (did the OLD traces violate
                             them?) and GATING (does the NEW engine avoid
                             repeating those mistakes?). One source of truth
                             for "what does correct look like," two uses.
  TraceMiner + GoldenBuilder -- turn each historical failure into a durable
                             golden test case (goldens.json).
  eval_gated                -- a decorator that attaches a `.run_gate()`
                             capability to the personalisation pipeline
                             function itself: call the function normally to
                             generate one offer, call `.run_gate()` to
                             re-run it against every golden and log a
                             promote/reject verdict (eval_runs.json).

The improvement loop this lab is named for: mine failures -> capture them as
goldens -> prove the CURRENT engine doesn't repeat them -> only then would a
real team promote it. Note what ISN'T here: a second, hand-tuned "candidate"
engine. The candidate is just your correct implementation of
PersonalisationEngine -- the eval gate exists to prove that engine actually
fixes what the old one got wrong, not to compare two arbitrary versions.

New SDK surface this lab uses: prompt caching (`cache_control` on the offer
catalog's static reference block in draft_offer_message) -- the pattern for
any system prompt with a large, reused-across-calls static portion.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_CHEAP = "claude-haiku-4-5-20251001"
MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "banking_customers.json", encoding="utf-8") as f:
    _CUSTOMERS_DATA = json.load(f)
    CREDIT_BAND_RANK = _CUSTOMERS_DATA["credit_band_rank"]
    CUSTOMERS = _CUSTOMERS_DATA["customers"]
with open(DATA_DIR / "banking_offer_catalog.json", encoding="utf-8") as f:
    CATALOG = json.load(f)
with open(DATA_DIR / "banking_traces.json", encoding="utf-8") as f:
    TRACES = json.load(f)["traces"]

CUSTOMERS_BY_ID = {c["customer_id"]: c for c in CUSTOMERS}
GOLDENS_FILE = DATA_DIR / "goldens.json"
EVAL_RUNS_FILE = DATA_DIR / "eval_runs.json"

client = Anthropic()


class RelevanceJudgment(BaseModel):
    passed: bool = Field(description="True if this offer is a sensible, well-targeted match for this customer.")
    reason: str = Field(description="One short sentence justifying the verdict.")


# ---------------------------------------------------------------------------
# QA check registry (given) -- the plugin/registry pattern: a check is just a
# function decorated with @register_check("name"); run_all_checks() doesn't
# know or care how many are registered.
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: dict[str, Callable[[dict, dict], dict]] = {}


def register_check(name: str):
    def decorator(fn: Callable[[dict, dict], dict]) -> Callable[[dict, dict], dict]:
        _CHECK_REGISTRY[name] = fn
        return fn
    return decorator


def run_all_checks(output: dict, customer: dict) -> dict:
    """Given — output is {"product_offered": str|None, "message": str}.
    Returns {check_name: {"passed": bool, "detail": str}} for every
    registered check."""
    return {name: fn(output, customer) for name, fn in _CHECK_REGISTRY.items()}


@register_check("eligibility_respected")
def check_eligibility_respected(output: dict, customer: dict) -> dict:
    product_id = output.get("product_offered")
    if product_id is None:
        return {"passed": True, "detail": "no product offered"}
    eligible_ids = {c["product_id"] for c in PersonalisationEngine.rank_offers(customer)}
    if product_id in eligible_ids:
        return {"passed": True, "detail": "ok"}
    return {"passed": False, "detail": f"{product_id} is not currently eligible for {customer['customer_id']}"}


@register_check("no_banned_phrase")
def check_no_banned_phrase(output: dict, customer: dict) -> dict:
    text = output.get("message", "").lower()
    hits = [phrase for phrase in CATALOG["banned_phrases"] if phrase in text]
    if hits:
        return {"passed": False, "detail": f"contains banned phrase(s): {hits}"}
    return {"passed": True, "detail": "ok"}


@register_check("required_disclosure_present")
def check_required_disclosure(output: dict, customer: dict) -> dict:
    product_id = output.get("product_offered")
    if product_id is None:
        return {"passed": True, "detail": "no product offered"}
    required = CATALOG["products"][product_id]["required_disclosure"]
    if required.lower() in output.get("message", "").lower():
        return {"passed": True, "detail": "ok"}
    return {"passed": False, "detail": f'missing verbatim disclosure: "{required}"'}


@register_check("relevance_judge")
def check_relevance_judge(output: dict, customer: dict) -> dict:
    """The one subjective check — a real haiku call, forced tool use."""
    product_id = output.get("product_offered")
    if product_id is None:
        return {"passed": True, "detail": "no product offered"}
    product = CATALOG["products"][product_id]
    system = (
        "You are a QA reviewer judging whether a personalized banking offer is well-targeted. Given "
        "the customer's profile and the message they were sent, decide whether the offer is a sensible, "
        "relevant match for THIS customer — not whether it's compliant, that's checked separately."
    )
    user = (
        f"Customer: segment={customer['segment']}, credit_band={customer['credit_band']}, "
        f"balance=${customer['balance']}, products_held={customer['products_held']}\n"
        f"Offered: {product['name']}\nMessage sent: {output.get('message')}"
    )
    response = client.messages.create(
        model=MODEL_CHEAP, max_tokens=300, system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{"name": "judge", "description": "Return the relevance judgment.",
                "input_schema": RelevanceJudgment.model_json_schema()}],
        tool_choice={"type": "tool", "name": "judge"},
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    result = RelevanceJudgment(**tool_call.input)
    return {"passed": result.passed, "detail": result.reason}


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

class PersonalisationEngine:
    """Deterministic. Hard-filters to what this customer is actually
    allowed to be offered, then scores the survivors — filtering answers
    "is this legal to offer," scoring answers "which legal offer is best.\""""

    @staticmethod
    def rank_offers(customer: dict) -> list[dict]:
        customer_rank = CREDIT_BAND_RANK[customer["credit_band"]]
        declined = {o["product"] for o in customer["prior_offers_shown"] if o["response"] == "declined"}
        candidates = []
        for product_id, product in CATALOG["products"].items():
            if customer["segment"] not in product["segment_fit"]:
                continue
            if customer_rank < CREDIT_BAND_RANK[product["min_credit_band"]]:
                continue
            if customer["balance"] < product["min_balance"]:
                continue
            if product_id in customer["products_held"]:
                continue
            if product_id in declined:
                continue
            affordability_bonus = (
                (1.0 if customer["balance"] >= 2 * product["min_balance"] else 0.5)
                if product["min_balance"] > 0 else 0.5
            )
            primary_fit_bonus = 1.0 if customer["segment"] == product["segment_fit"][0] else 0.0
            score = customer_rank + affordability_bonus + primary_fit_bonus
            candidates.append({"product_id": product_id, "score": round(score, 2)})
        return sorted(candidates, key=lambda c: c["score"], reverse=True)


def _catalog_reference_block() -> str:
    """Given — the static, reused-every-call portion of the drafting
    prompt. Built once at import time, cached via cache_control below."""
    lines = ["Product catalog:"]
    for product_id, product in CATALOG["products"].items():
        lines.append(
            f"- {product_id} ({product['name']}): {', '.join(product['pitch_points'])}. "
            f'Required disclosure (verbatim): "{product["required_disclosure"]}"'
        )
    lines.append(f"Never use these phrases: {', '.join(CATALOG['banned_phrases'])}")
    return "\n".join(lines)


CATALOG_REFERENCE_BLOCK = _catalog_reference_block()


def draft_offer_message(customer: dict, product_id: str, prior_facts: list[str]) -> str:
    """Real sonnet call. `system` is a list of two blocks on purpose: the
    short per-call instruction stays uncached (it never repeats verbatim),
    the catalog reference block carries cache_control — it's identical on
    every call this process makes, in mining, campaign drafting, AND every
    eval-gate re-run. (At this lab's toy catalog size the block is well
    under the ~1024-token minimum a cache write actually needs — the point
    here is the mechanism; a real policy/catalog doc clears that bar
    easily.)"""
    system = [
        {
            "type": "text",
            "text": (
                "You write short, personalized outbound banking offer messages. Address the customer "
                "by first name, mention 1-2 concrete pitch points for the SPECIFIC product you were "
                "asked to pitch, and include that product's required disclosure verbatim, unmodified, "
                "as the final sentence. Never use an absolute or overpromising claim."
            ),
        },
        {"type": "text", "text": CATALOG_REFERENCE_BLOCK, "cache_control": {"type": "ephemeral"}},
    ]
    user = (
        f"Customer: {customer['name'].split()[0]}, segment={customer['segment']}\n"
        f"Product to pitch: {product_id}\nPrior contact history: {prior_facts or '(first contact)'}"
    )
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=250, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


def generate_personalized_offer(customer: dict) -> dict:
    """The pipeline eval_gated wraps below. Picks the top-ranked eligible
    product (or a clean no-offer fallback), pulls this customer's own
    prior-offer history into the drafting call — a repeat contact reads
    its own memory, no separate store needed since the fixture already
    carries it."""
    ranked = PersonalisationEngine.rank_offers(customer)
    if not ranked:
        return {
            "product_offered": None,
            "message": f"No eligible personalized offer for {customer['customer_id']} right now.",
        }
    top_product_id = ranked[0]["product_id"]
    prior_facts = [f"{o['product']}: {o['response']}" for o in customer["prior_offers_shown"]]
    message = draft_offer_message(customer, top_product_id, prior_facts)
    return {"product_offered": top_product_id, "message": message}


# ---------------------------------------------------------------------------
# Mining, goldens, and the eval gate
# ---------------------------------------------------------------------------

class TraceMiner:
    @staticmethod
    def mine(traces: list[dict]) -> list[dict]:
        """Run the full check registry over every historical trace. A
        trace with ANY failing check is returned with which checks failed
        and why — this never calls the live engine, only judges what
        already happened."""
        failing = []
        for trace in traces:
            customer = CUSTOMERS_BY_ID[trace["customer_id"]]
            output = {"product_offered": trace["product_offered"], "message": trace["drafted_message"]}
            checks = run_all_checks(output, customer)
            failed = {name: result["detail"] for name, result in checks.items() if not result["passed"]}
            if failed:
                failing.append({
                    "trace_id": trace["trace_id"],
                    "customer_id": trace["customer_id"],
                    "failed_checks": failed,
                })
        return failing


class GoldenBuilder:
    @staticmethod
    def promote(failing_traces: list[dict], goldens_path: Path = GOLDENS_FILE) -> list[dict]:
        """Appends one golden per NEW failing customer_id (skips a
        customer already captured, so re-running the miner doesn't grow
        goldens.json without bound). Returns only the newly-added
        goldens."""
        goldens = json.load(open(goldens_path, encoding="utf-8")) if goldens_path.exists() else []
        existing_ids = {g["customer_id"] for g in goldens}
        added = []
        for trace in failing_traces:
            if trace["customer_id"] in existing_ids:
                continue
            golden = {
                "golden_id": f"GOLD-{len(goldens) + 1:03d}",
                "customer_id": trace["customer_id"],
                "source_trace_id": trace["trace_id"],
                "failed_checks_at_capture": list(trace["failed_checks"].keys()),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
            goldens.append(golden)
            existing_ids.add(trace["customer_id"])
            added.append(golden)
        with open(goldens_path, "w", encoding="utf-8") as f:
            json.dump(goldens, f, ensure_ascii=False, indent=2)
        return added


def eval_gated(goldens_path: Path, pass_threshold: float = 1.0, eval_log_path: Path = EVAL_RUNS_FILE):
    """A decorator that does NOT change how the decorated function behaves
    on a normal call — it attaches a `.run_gate()` capability alongside it.
    `some_pipeline(customer)` still just generates one offer;
    `some_pipeline.run_gate()` re-runs it against every captured golden and
    logs a promote/reject verdict. That split (normal call vs. CI-style
    gate check, same function) is the "eval-gated update" pattern."""

    def decorator(pipeline_fn):
        def run_gate() -> dict:
            if not goldens_path.exists():
                return {"pass_rate": None, "promoted": False, "results": [], "detail": "no goldens captured yet"}
            goldens = json.load(open(goldens_path, encoding="utf-8"))
            results = []
            for golden in goldens:
                customer = CUSTOMERS_BY_ID[golden["customer_id"]]
                output = pipeline_fn(customer)
                checks = run_all_checks(output, customer)
                passed = all(result["passed"] for result in checks.values())
                results.append({
                    "golden_id": golden["golden_id"],
                    "customer_id": golden["customer_id"],
                    "passed": passed,
                    "checks": {name: result["passed"] for name, result in checks.items()},
                })
            pass_rate = round(sum(1 for r in results if r["passed"]) / len(results), 3) if results else 0.0
            run_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "candidate": pipeline_fn.__name__,
                "pass_rate": pass_rate,
                "promoted": pass_rate >= pass_threshold,
                "results": results,
            }
            history = json.load(open(eval_log_path, encoding="utf-8")) if eval_log_path.exists() else []
            history.append(run_record)
            with open(eval_log_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            return run_record

        pipeline_fn.run_gate = run_gate
        return pipeline_fn

    return decorator


generate_personalized_offer = eval_gated(goldens_path=GOLDENS_FILE)(generate_personalized_offer)


class ImprovementLoop:
    """Given — the one function you'd actually schedule nightly: mine
    yesterday's traces, capture new failures as goldens, and prove the
    CURRENT engine clears the whole accumulated suite."""

    @staticmethod
    def run_cycle(traces: list[dict]) -> dict:
        failing = TraceMiner.mine(traces)
        newly_promoted = GoldenBuilder.promote(failing)
        gate_result = generate_personalized_offer.run_gate()
        return {
            "traces_scanned": len(traces),
            "traces_failing": len(failing),
            "goldens_newly_promoted": len(newly_promoted),
            "gate_result": gate_result,
        }


if __name__ == "__main__":
    print(f"=== Lab-2: Banking Personalisation + QA Loop — {len(CUSTOMERS)} customers ===\n")

    print("--- PersonalisationEngine.rank_offers (deterministic, free) ---")
    for customer in CUSTOMERS:
        ranked = PersonalisationEngine.rank_offers(customer)
        summary = ranked[0]["product_id"] if ranked else "(no eligible product)"
        print(f"  {customer['customer_id']} ({customer['segment']}, {customer['credit_band']}): "
              f"{[c['product_id'] for c in ranked]} -> top={summary}")

    print(f"\n--- Generating today's campaign ({len(CUSTOMERS)} real drafting calls) ---")
    for customer in CUSTOMERS:
        offer = generate_personalized_offer(customer)
        if offer["product_offered"]:
            print(f"  {customer['customer_id']}: {offer['product_offered']}")
            print(f"    \"{offer['message']}\"")
        else:
            print(f"  {customer['customer_id']}: {offer['message']}")

    print(f"\n--- Improvement-loop cycle over {len(TRACES)} historical traces ---")
    cycle = ImprovementLoop.run_cycle(TRACES)
    print(f"  Traces scanned: {cycle['traces_scanned']}")
    print(f"  Traces failing QA: {cycle['traces_failing']}")
    print(f"  Newly promoted goldens: {cycle['goldens_newly_promoted']}")

    gate = cycle["gate_result"]
    verdict = "PROMOTED" if gate["promoted"] else "REJECTED"
    print(f"\n--- Eval gate verdict: {verdict} (pass_rate={gate['pass_rate']}) ---")
    for result in gate["results"]:
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"  [{mark}] {result['golden_id']} ({result['customer_id']}): {result['checks']}")

    print(f"\n--- Persisted: {GOLDENS_FILE.name}, {EVAL_RUNS_FILE.name} ---")

# Expected (hand-verified against banking_customers.json / banking_traces.json):
# rank_offers top pick per customer: B01->cashback_card, B02->high_yield_savings,
# B03->starter_credit_builder, B04->(none — segment fits nothing left after
# already holding its only match), B05->retiree_travel_rewards_card,
# B06->cashback_card, B07->high_yield_savings, B08->starter_credit_builder
# (beats cashback_card on primary-fit score, 2.5 vs 1.5), B09->(none — already
# holds its only fit), B10->retiree_travel_rewards_card (beats high_yield_savings,
# 3.5 vs 2.5). rank_offers/no_banned_phrase/required_disclosure_present are fully
# deterministic and guarantee AT LEAST 6 of 13 traces fail mining: TR-03 (missing
# disclosure), TR-04 (eligibility — wrong segment), TR-06/TR-12 (banned phrase,
# two different phrases), TR-07 (eligibility — declined + balance), TR-09
# (eligibility — already held) -> goldens for B01/B03/B04/B06/B07/B09, guaranteed.
# relevance_judge is a REAL model call, and TraceMiner runs the FULL registry
# (judge included) over the historical traces too, not just the eval gate — so
# mining can promote MORE than 6 goldens if the judge flags an otherwise-clean
# historical trace as poorly targeted (observed in testing: 8/13 failed, with
# B05 and B10 added on judge grounds). Don't hardcode "6" as the count students
# should see. Similarly, the eval gate's pass_rate over an otherwise-correct
# engine should be high but is NOT guaranteed 1.0 — a single relevance_judge
# false-negative on a genuinely well-targeted offer is expected occasional
# variance (observed in testing: pass_rate=0.875, REJECTED, on a single golden
# where every deterministic check passed and only the judge disagreed). Read the
# per-golden "checks" breakdown before concluding your implementation is wrong;
# if every FAIL is judge-only, that's the discussion prompt (see README), not a bug.
