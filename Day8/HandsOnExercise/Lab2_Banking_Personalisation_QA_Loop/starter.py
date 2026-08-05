"""
Lab-2: Banking - Ship a Smarter Offer Engine Without Shipping a Bad One (STARTER).

banking_traces.json is 13 historical personalization sends — a log of what
SOME engine already offered ten banking customers before this lab existed.
Six of those thirteen have a real problem: an ineligible product, a missing
disclosure, a banned phrase. Nobody caught them at the time, because nobody
was running continuous QA.

This lab builds that QA loop, and the ENGINE it protects, together. You'll
build:
  1. Three deterministic QA checks (eligibility_respected, no_banned_phrase,
     required_disclosure_present) + the LLM-judge check (relevance_judge).
     The registry (@register_check / run_all_checks) is given — you're
     writing what gets registered, not the registry itself.
  2. PersonalisationEngine.rank_offers — hard-filter to what's legal to
     offer, score the survivors.
  3. draft_offer_message + generate_personalized_offer — the real drafting
     call (with prompt caching on the catalog reference block) and the
     pipeline that wraps it.
  4. TraceMiner.mine — run the registry over banking_traces.json, collect
     failures.
  5. GoldenBuilder.promote — turn new failures into durable goldens.json
     entries.
  6. eval_gated — the decorator that attaches `.run_gate()` to the
     pipeline, and ImprovementLoop.run_cycle to wire steps 4-6 together.

New SDK surface this lab uses: prompt caching (`cache_control` on the offer
catalog's static reference block) — the pattern for any system prompt with
a large, reused-across-calls static portion.

Given, not a TODO: EvalDashboard (reads eval_runs.json back and plots
pass_rate as a trend line) and the __main__ ordering below, which runs the
improvement-loop gate BEFORE generating today's campaign and skips the send
entirely if the gate rejects — the lab's title is "without shipping a bad
one," so the campaign has to wait on the gate, not the other way around.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
EVAL_DASHBOARD_FILE = DATA_DIR / "eval_dashboard.png"

client = Anthropic()

# Chart chrome — same dataviz-skill palette Lab-1 and the Capstone use.
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
CATEGORICAL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a"}


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
    """
    TODO 1a: If output["product_offered"] is None, pass trivially (nothing
    was offered, nothing to violate). Otherwise compute this customer's
    currently-eligible product ids via PersonalisationEngine.rank_offers
    and fail if the offered product isn't among them. detail should say
    which product wasn't eligible for which customer_id on failure, "ok"
    on pass.
    """
    raise NotImplementedError


@register_check("no_banned_phrase")
def check_no_banned_phrase(output: dict, customer: dict) -> dict:
    """
    TODO 1b: Case-insensitive substring check of output["message"] against
    CATALOG["banned_phrases"]. Fail (listing which phrase(s) hit) if any
    are present, else pass.
    """
    raise NotImplementedError


@register_check("required_disclosure_present")
def check_required_disclosure(output: dict, customer: dict) -> dict:
    """
    TODO 1c: If output["product_offered"] is None, pass trivially. Else
    look up CATALOG["products"][product_id]["required_disclosure"] and
    fail unless it appears VERBATIM (case-insensitive is fine) in
    output["message"].
    """
    raise NotImplementedError


@register_check("relevance_judge")
def check_relevance_judge(output: dict, customer: dict) -> dict:
    """
    TODO 2: The one subjective check — real haiku call, forced tool use.
    If output["product_offered"] is None, pass trivially (nothing to
    judge). Otherwise: system prompt explains this is a QA reviewer
    judging whether the offer is a sensible, well-targeted match for this
    customer (not compliance — that's the other checks' job); user content
    = customer's segment/credit_band/balance/products_held + the offered
    product's name + the message that was sent. Force a tool call on
    RelevanceJudgment.model_json_schema(), parse it, return
    {"passed": result.passed, "detail": result.reason}.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

class PersonalisationEngine:
    """Deterministic. Hard-filters to what this customer is actually
    allowed to be offered, then scores the survivors — filtering answers
    "is this legal to offer," scoring answers "which legal offer is best.\""""

    @staticmethod
    def rank_offers(customer: dict) -> list[dict]:
        """
        TODO 3: For every product in CATALOG["products"], HARD-EXCLUDE if
        any of: customer["segment"] not in product["segment_fit"]; this
        customer's credit_band ranks below product["min_credit_band"]
        (use CREDIT_BAND_RANK for both sides); customer["balance"] <
        product["min_balance"]; the product_id is already in
        customer["products_held"]; the product_id appears in this
        customer's prior_offers_shown with response == "declined".
        For survivors, score = credit_band_rank(customer) +
        affordability_bonus + primary_fit_bonus, where affordability_bonus
        is 1.0 if balance >= 2x the product's min_balance else 0.5 (and
        min_balance == 0 always gets 0.5), and primary_fit_bonus is 1.0
        only if the customer's segment is segment_fit[0] (the product's
        PRIMARIES get a bonus survivors in a secondary segment don't).
        Return survivors as [{"product_id":..., "score": round(...,2)}],
        sorted highest score first.
        """
        raise NotImplementedError


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
    """
    TODO 4a: Real sonnet call. Build `system` as a list of TWO blocks:
      1. {"type": "text", "text": <instruction>} — no cache_control. The
         instruction: write a short personalized outbound banking offer
         message, address the customer by first name, mention 1-2 concrete
         pitch points for the SPECIFIC product being pitched, include that
         product's required disclosure verbatim as the final sentence,
         never use an absolute/overpromising claim.
      2. {"type": "text", "text": CATALOG_REFERENCE_BLOCK, "cache_control":
         {"type": "ephemeral"}} — this one's identical on every call this
         process makes (mining re-checks, campaign drafting, every eval-gate
         re-run), which is exactly what a cache breakpoint is for.
    user content: customer's first name + segment, the product_id to pitch,
    and prior_facts (or "(first contact)" if empty).
    client.messages.create(model=MODEL_DRAFT, max_tokens=250, system=...,
    messages=[{"role": "user", "content": ...}]) — return the text block,
    stripped.
    """
    raise NotImplementedError


def generate_personalized_offer(customer: dict) -> dict:
    """
    TODO 4b: Rank this customer's offers. If none, return
    {"product_offered": None, "message": <a clean "no eligible offer right
    now" sentence mentioning their customer_id>}. Otherwise take the
    TOP-ranked product_id, build prior_facts as a list of
    "{product}: {response}" strings from customer["prior_offers_shown"]
    (a repeat contact should read its own history), call
    draft_offer_message, and return {"product_offered": top_product_id,
    "message": <the draft>}.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Mining, goldens, and the eval gate
# ---------------------------------------------------------------------------

class TraceMiner:
    @staticmethod
    def mine(traces: list[dict]) -> list[dict]:
        """
        TODO 5: For each trace, look up its customer via CUSTOMERS_BY_ID,
        build output = {"product_offered": trace["product_offered"],
        "message": trace["drafted_message"]}, and run_all_checks(output,
        customer). If any check's "passed" is False, append a record:
        {"trace_id":..., "customer_id":..., "failed_checks": {name: detail
        for every FAILING check}}. A trace where everything passes
        contributes nothing. Return the list of failing records. This
        never calls generate_personalized_offer — it only judges what the
        historical trace already says happened.
        """
        raise NotImplementedError


class GoldenBuilder:
    @staticmethod
    def promote(failing_traces: list[dict], goldens_path: Path = GOLDENS_FILE) -> list[dict]:
        """
        TODO 6a: Load goldens_path if it exists (a JSON list), else start
        empty. Skip any failing trace whose customer_id is ALREADY
        represented in goldens (re-running the miner shouldn't grow the
        file without bound). For each new one, append {"golden_id":
        f"GOLD-{n:03d}" (n = current length + 1), "customer_id":...,
        "source_trace_id":..., "failed_checks_at_capture": <list of the
        failed check names>, "captured_at": <UTC ISO timestamp>}. Write
        the whole list back (indent=2). Return only the newly-added
        goldens.
        """
        raise NotImplementedError


def eval_gated(goldens_path: Path, pass_threshold: float = 1.0, eval_log_path: Path = EVAL_RUNS_FILE):
    """A decorator that does NOT change how the decorated function behaves
    on a normal call — it attaches a `.run_gate()` capability alongside
    it. The outer wiring (this bit) is given; TODO 6b is `run_gate`'s
    body — note `raise NotImplementedError` lives INSIDE run_gate, not in
    decorator() itself, so decorating generate_personalized_offer below
    doesn't blow up the whole module before you've even reached TODO 6b —
    it only fails once something actually calls .run_gate()."""

    def decorator(pipeline_fn):
        def run_gate() -> dict:
            """
            TODO 6b: Load goldens_path (return {"pass_rate": None,
            "promoted": False, "results": [], "detail": "no goldens
            captured yet"} if it doesn't exist yet — this loop hasn't run
            once). For each golden: look up its customer via
            CUSTOMERS_BY_ID, call `pipeline_fn(customer)`, run_all_checks
            on the output, and record whether EVERY check passed. Compute
            pass_rate = passed_count / total (round 3dp, guard the
            zero-goldens case). Build a run record: {"timestamp": <UTC ISO>,
            "candidate": pipeline_fn.__name__, "pass_rate":...,
            "promoted": pass_rate >= pass_threshold, "results": [{
            "golden_id":..., "customer_id":..., "passed":...,
            "checks": {name: passed_bool}} per golden]}. Load-or-start-empty
            eval_log_path the same way GoldenBuilder does, append this
            record, write it back, and return the record.
            """
            raise NotImplementedError

        pipeline_fn.run_gate = run_gate
        return pipeline_fn

    return decorator


generate_personalized_offer = eval_gated(goldens_path=GOLDENS_FILE)(generate_personalized_offer)


class EvalDashboard:
    """Given — every `.run_gate()` call already appends a record to
    eval_runs.json; this reads that file back and plots it, so running the
    gate more than once actually shows a trend, not just another snapshot."""

    @staticmethod
    def build(eval_history: list[dict], out_path: Path) -> None:
        fig, ax = plt.subplots(figsize=(7, 4), facecolor=SURFACE)
        ax.set_facecolor(SURFACE)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(INK_MUTED)
        ax.tick_params(colors=INK_MUTED, labelsize=9)
        ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)

        run_idx = list(range(1, len(eval_history) + 1))
        pass_rates = [r["pass_rate"] if r["pass_rate"] is not None else 0.0 for r in eval_history]

        if len(eval_history) >= 2:
            ax.plot(run_idx, pass_rates, color=CATEGORICAL["blue"], linewidth=2, marker="o", markersize=5, zorder=3)
        elif eval_history:
            ax.plot(run_idx, pass_rates, color=CATEGORICAL["blue"], marker="o", markersize=6, zorder=3)
            ax.set_xlim(0, 2)
            ax.text(0.5, 0.1, "needs 2+ gate runs for a line", transform=ax.transAxes, ha="center",
                     color=INK_MUTED, fontsize=8)
        else:
            ax.text(0.5, 0.5, "no gate runs logged yet", transform=ax.transAxes, ha="center", va="center",
                     color=INK_MUTED, fontsize=9)
        ax.axhline(1.0, color=INK_MUTED, linewidth=0.8, linestyle="--", zorder=2)
        ax.set_ylim(-0.05, 1.1)
        ax.set_xticks(run_idx)
        ax.set_title(f"Eval-gate pass rate across runs (n={len(eval_history)})", color=INK, fontsize=11, loc="left", fontweight="bold")

        fig.tight_layout()
        fig.savefig(out_path, dpi=130, facecolor=SURFACE)
        plt.close(fig)


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

    # Gate BEFORE campaign, not after: this lab's whole thesis is shipping a
    # smarter engine WITHOUT shipping a bad one — running the gate after the
    # send would mean you already shipped the bad one by the time you found out.
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

    eval_history = json.load(open(EVAL_RUNS_FILE, encoding="utf-8")) if EVAL_RUNS_FILE.exists() else []
    EvalDashboard.build(eval_history, EVAL_DASHBOARD_FILE)
    print(f"  Eval dashboard written -> {EVAL_DASHBOARD_FILE.name} ({len(eval_history)} gate run(s) in trend)")

    if gate["promoted"]:
        print(f"\n--- Gate PROMOTED — generating today's campaign ({len(CUSTOMERS)} real drafting calls) ---")
        for customer in CUSTOMERS:
            offer = generate_personalized_offer(customer)
            if offer["product_offered"]:
                print(f"  {customer['customer_id']}: {offer['product_offered']}")
                print(f"    \"{offer['message']}\"")
            else:
                print(f"  {customer['customer_id']}: {offer['message']}")
    else:
        print(f"\n--- Gate REJECTED (pass_rate={gate['pass_rate']}) — campaign send SKIPPED ---")
        print("  Fix the failing goldens above and rerun before shipping today's campaign.")

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
