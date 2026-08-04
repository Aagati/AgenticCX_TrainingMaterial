"""
Capstone: Insurance - Prove the Loop Works Before a Real Customer Sees It.

Every mechanic Day 8 taught, fused into one cycle: turn a batch of
historical claim-support traces into numbers (Lab-1), mine them for
compliance failures and gate a fix behind a golden suite before it ships
(Lab-2), grounded in a policy knowledge base (Lab-3's idea, given here
rather than built — see below).

WHY THIS COHORT GETS THE KNOWLEDGE BASE PRE-BUILT: Lab-3 is this day's
self-paced lab — there's a real chance it never got facilitator time or
even a solo pass before this capstone. So `KnowledgeBase` ships complete,
explained inline, not a TODO. What you BUILD instead is everything from
Lab-1 (AnalyticsEngine) and Lab-2 (the QA checks, mining, the
personalisation+drafting agent, the eval gate) — the two labs that WERE
facilitator-led. This capstone tests what you were actually taught, not
what you were handed a self-paced README for and may never have opened.

WHY THIS IS A GRAPH: analytics and mining are batch-level — they run ONCE
over every trace, no branching. The part that genuinely needs to be a graph
is per-golden: draft a response, judge it, and if it fails, revise it and
judge it AGAIN — a specialist correcting its own work against feedback,
capped at one retry. A flat function chain can't express that cycle as
cleanly as an actual graph edge back to the judging node can.

WHY MINING IS DETERMINISTIC-ONLY HERE (a change from Lab-2): Lab-2 let its
LLM-judge check run during mining too, and real testing there showed it
adding EXTRA failures beyond the deterministic ones — authentic, but
unpredictable, which is a poor property for a check this capstone's own
self-check needs to hard-assert against. Here, `run_checks(...,
deterministic_only=True)` is what QAMiner uses; the judge is reserved for
gating a LIVE candidate response, where "a human-like reviewer's opinion"
is actually the right question to be asking.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from anthropic import Anthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_CHEAP = "claude-haiku-4-5-20251001"
MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "insurance_kb_articles.json", encoding="utf-8") as f:
    _KB_DATA = json.load(f)
    REQUIRED_DISCLOSURE = _KB_DATA["required_disclosure"]
    BANNED_PHRASES = _KB_DATA["banned_phrases"]
    KB_ARTICLES = _KB_DATA["articles"]
with open(DATA_DIR / "insurance_customers.json", encoding="utf-8") as f:
    CUSTOMERS = json.load(f)["customers"]
with open(DATA_DIR / "claim_traces.json", encoding="utf-8") as f:
    CLAIM_TRACES = json.load(f)["traces"]

KB_ARTICLES_BY_ID = {a["article_id"]: a for a in KB_ARTICLES}
CUSTOMERS_BY_ID = {c["customer_id"]: c for c in CUSTOMERS}
GENERAL_ARTICLE_IDS = {a["article_id"] for a in KB_ARTICLES if set(a["policy_type"]) == {"auto", "home", "health"}}

GOLDENS_FILE = DATA_DIR / "capstone_goldens.json"
EVAL_RUNS_FILE = DATA_DIR / "capstone_eval_runs.json"
DASHBOARD_FILE = DATA_DIR / "capstone_dashboard.png"

client = Anthropic()

INK = "#0b0b0b"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
CATEGORICAL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a"}

EXPECTED_FAILING_CUSTOMER_IDS = {"CUST-C01", "CUST-C03", "CUST-C04", "CUST-C05"}


class RelevanceJudgment(BaseModel):
    passed: bool = Field(description="True if this response is a sensible, well-grounded answer to the customer's question.")
    reason: str = Field(description="One short sentence justifying the verdict.")


class CycleState(TypedDict, total=False):
    golden: dict
    customer: dict
    article: dict | None
    response_text: str | None
    checks: dict | None
    passed: bool
    repair_attempted: bool
    outcome: str | None


# ---------------------------------------------------------------------------
# QA check registry (given infrastructure — same registry/decorator pattern
# as Lab-2, extended with a `deterministic` flag so mining and gating can
# each ask for a different slice of the same registry).
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: dict[str, dict] = {}


def register_check(name: str, deterministic: bool = True):
    def decorator(fn):
        _CHECK_REGISTRY[name] = {"fn": fn, "deterministic": deterministic}
        return fn
    return decorator


def run_checks(output: dict, customer: dict, deterministic_only: bool = False) -> dict:
    """Given — output is {"article_cited": str|None, "response_text": str}."""
    results = {}
    for name, entry in _CHECK_REGISTRY.items():
        if deterministic_only and not entry["deterministic"]:
            continue
        results[name] = entry["fn"](output, customer)
    return results


@register_check("policy_type_respected")
def check_policy_type_respected(output: dict, customer: dict) -> dict:
    article_id = output.get("article_cited")
    if article_id is None:
        return {"passed": True, "detail": "no article cited"}
    article = KB_ARTICLES_BY_ID[article_id]
    if customer["policy_type"] in article["policy_type"]:
        return {"passed": True, "detail": "ok"}
    return {"passed": False, "detail": f"{article_id} does not apply to policy_type={customer['policy_type']}"}


@register_check("no_banned_phrase")
def check_no_banned_phrase(output: dict, customer: dict) -> dict:
    text = output.get("response_text", "").lower()
    hits = [phrase for phrase in BANNED_PHRASES if phrase in text]
    if hits:
        return {"passed": False, "detail": f"contains banned phrase(s): {hits}"}
    return {"passed": True, "detail": "ok"}


@register_check("required_disclosure_present")
def check_required_disclosure(output: dict, customer: dict) -> dict:
    if REQUIRED_DISCLOSURE.lower() in output.get("response_text", "").lower():
        return {"passed": True, "detail": "ok"}
    return {"passed": False, "detail": f'missing verbatim disclosure: "{REQUIRED_DISCLOSURE}"'}


@register_check("relevance_judge", deterministic=False)
def check_relevance_judge(output: dict, customer: dict) -> dict:
    """The one subjective check — real haiku call, forced tool use. Used
    by the eval gate; deliberately NOT used by QAMiner (see module
    docstring)."""
    article_id = output.get("article_cited")
    if article_id is None:
        return {"passed": True, "detail": "no article cited"}
    article = KB_ARTICLES_BY_ID[article_id]
    system = (
        "You are a QA reviewer judging whether an insurance claim-support response is well-grounded and "
        "actually answers the customer's question — not whether it's compliant, that's checked separately."
    )
    user = (
        f"Customer question: {customer.get('pending_question', '(unspecified)')}\n"
        f"Policy type: {customer['policy_type']}\nArticle cited: {article['title']}\n"
        f"Response: {output.get('response_text')}"
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
# Knowledge base (GIVEN — Lab-3's idea, thinned: deterministic keyword
# scoring, hard-filtered to this customer's policy_type. That hard filter
# is why policy_type_respected trivially passes anything retrieved here —
# the check exists to catch responses that DIDN'T come through this
# function, i.e. the historical traces.)
# ---------------------------------------------------------------------------

class KnowledgeBase:
    @staticmethod
    def retrieve(query: str, policy_type: str, top_k: int = 1) -> list[dict]:
        query_lower = query.lower()
        candidates = [a for a in KB_ARTICLES if policy_type in a["policy_type"]]
        scored = []
        for article in candidates:
            tag_hits = sum(1 for tag in article["tags"] if tag.lower() in query_lower)
            if tag_hits > 0:
                scored.append({**article, "score": tag_hits})
        scored.sort(key=lambda a: a["score"], reverse=True)
        if scored:
            return scored[:top_k]
        # nothing matched by keyword -- fall back to this policy's general articles
        general = [a for a in candidates if a["article_id"] in GENERAL_ARTICLE_IDS]
        return general[:top_k]


# ---------------------------------------------------------------------------
# Lab-1 content: analytics over the raw trace log
# ---------------------------------------------------------------------------

class AnalyticsEngine:
    @staticmethod
    def compute(traces: list[dict]) -> dict:
        policy_types = Counter(CUSTOMERS_BY_ID[t["customer_id"]]["policy_type"] for t in traces)
        cited = Counter(t["article_cited"] for t in traces)
        return {
            "total_traces": len(traces),
            "volume_by_policy_type": dict(policy_types),
            "top_cited_articles": cited.most_common(5),
        }


class Dashboard:
    """Given — same chart chrome as Lab-1's Dashboard, two panels instead
    of four. Nothing new here; reusing a working mechanism on new data."""

    @staticmethod
    def build(metrics: dict, out_path: Path) -> None:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), facecolor=SURFACE)
        for ax in axes:
            ax.set_facecolor(SURFACE)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(INK_MUTED)
            ax.tick_params(colors=INK_MUTED, labelsize=9)
            ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
            ax.set_axisbelow(True)

        ax = axes[0]
        policy_colors = {"auto": CATEGORICAL["blue"], "home": CATEGORICAL["orange"], "health": CATEGORICAL["aqua"]}
        types = list(metrics["volume_by_policy_type"].keys())
        bars = ax.bar(types, [metrics["volume_by_policy_type"][t] for t in types],
                       color=[policy_colors.get(t, INK_MUTED) for t in types], width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Claim volume by policy type", color=INK, fontsize=11, loc="left", fontweight="bold")

        ax = axes[1]
        top = metrics["top_cited_articles"]
        labels = [article_id for article_id, _ in top]
        counts = [count for _, count in top]
        bars = ax.barh(labels, counts, color=CATEGORICAL["blue"], height=0.6, zorder=3)
        ax.invert_yaxis()
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Most-cited articles", color=INK, fontsize=11, loc="left", fontweight="bold")

        fig.suptitle("Insurance Improvement Loop — Trace Analytics", color=INK, fontsize=13, fontweight="bold", x=0.02, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.94))
        fig.savefig(out_path, dpi=130, facecolor=SURFACE)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Lab-2 content: mining, goldens, the drafting agent, the eval gate
# ---------------------------------------------------------------------------

class QAMiner:
    @staticmethod
    def mine(traces: list[dict]) -> list[dict]:
        failing = []
        for trace in traces:
            customer = CUSTOMERS_BY_ID[trace["customer_id"]]
            output = {"article_cited": trace["article_cited"], "response_text": trace["response_text"]}
            checks = run_checks(output, customer, deterministic_only=True)
            failed = {name: result["detail"] for name, result in checks.items() if not result["passed"]}
            if failed:
                failing.append({"trace_id": trace["trace_id"], "customer_id": trace["customer_id"], "failed_checks": failed})
        return failing


class GoldenBuilder:
    """Given — identical shape to Lab-2's."""

    @staticmethod
    def promote(failing_traces: list[dict], goldens_path: Path = GOLDENS_FILE) -> list[dict]:
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


def draft_response(customer: dict, article: dict | None) -> str:
    """Real sonnet call. Tone is the personalisation axis here (segment),
    grounding is the KnowledgeBase's job — this function only drafts."""
    if article is None:
        return (
            f"Hi {customer['name'].split()[0]}, I don't have a specific article on hand for this yet — "
            f"connecting you with a specialist who can help directly. {REQUIRED_DISCLOSURE}"
        )
    tone = (
        "white-glove and proactive — offer to personally follow up"
        if customer["segment"] == "premium" else "friendly and direct"
    )
    system = (
        f"You are an insurance support assistant. Tone: {tone}. Answer using ONLY the provided article — "
        f"never invent a coverage detail that isn't in it. Include this exact disclosure verbatim as the "
        f"final sentence: \"{REQUIRED_DISCLOSURE}\" Never use an absolute claim like a guaranteed payout or "
        f"automatic approval — coverage always depends on policy review."
    )
    user = (
        f"Customer: {customer['name'].split()[0]}, policy_type={customer['policy_type']}\n"
        f"Question: {customer.get('pending_question', '(unspecified)')}\n"
        f"Article: {article['title']}\n{article['body']}"
    )
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=300, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


def response_agent_node(state: CycleState) -> dict:
    customer = state["customer"]
    articles = KnowledgeBase.retrieve(customer.get("pending_question", ""), customer["policy_type"], top_k=1)
    article = articles[0] if articles else None
    response_text = draft_response(customer, article)
    return {"article": article, "response_text": response_text}


def eval_gate_node(state: CycleState) -> dict:
    output = {
        "article_cited": state["article"]["article_id"] if state["article"] else None,
        "response_text": state["response_text"],
    }
    checks = run_checks(output, state["customer"], deterministic_only=False)
    passed = all(result["passed"] for result in checks.values())
    return {"checks": checks, "passed": passed}


def revise_node(state: CycleState) -> dict:
    """Given — one repair attempt, fed the SPECIFIC failing checks (same
    shape as Day7's brand-safety repair loop), explicitly re-instructed to
    keep the disclosure verbatim rather than trusting a generic "keep the
    rest intact" to preserve it through a rewrite."""
    problems = [f"{name}: {result['detail']}" for name, result in state["checks"].items() if not result["passed"]]
    system = (
        "You rewrite insurance claim-support responses to fix SPECIFIC compliance problems, keeping the "
        "rest of the message's intent and any correct information intact. The rewritten message MUST still "
        f"end with this exact disclosure sentence, verbatim: \"{REQUIRED_DISCLOSURE}\""
    )
    user = f"Original response: {state['response_text']}\n\nProblems to fix:\n" + "\n".join(problems)
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=300, system=system, messages=[{"role": "user", "content": user}]
    )
    revised = next(b for b in response.content if b.type == "text").text.strip()
    return {"response_text": revised, "repair_attempted": True}


def promote_node(state: CycleState) -> dict:
    return {"outcome": "promoted"}


def reject_node(state: CycleState) -> dict:
    return {"outcome": "rejected"}


def _route_after_gate(state: CycleState) -> Literal["promote", "revise", "reject"]:
    if state["passed"]:
        return "promote"
    if state.get("repair_attempted"):
        return "reject"
    return "revise"


class ImprovementCommandCenter:
    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self):
        """5 nodes, one cycle: response_agent -> eval_gate -> (promote |
        revise -> back to eval_gate | reject). Everything upstream of
        response_agent (analytics, mining) is plain batch Python in
        run_cycle below, not graph nodes — there's no per-item branching
        or looping in a batch computation, so a graph buys nothing there;
        the repair loop is the one place it earns its keep."""
        graph = StateGraph(CycleState)
        graph.add_node("response_agent", response_agent_node)
        graph.add_node("eval_gate", eval_gate_node)
        graph.add_node("revise", revise_node)
        graph.add_node("promote", promote_node)
        graph.add_node("reject", reject_node)

        graph.set_entry_point("response_agent")
        graph.add_edge("response_agent", "eval_gate")
        graph.add_conditional_edges("eval_gate", _route_after_gate, {
            "promote": "promote", "revise": "revise", "reject": "reject",
        })
        graph.add_edge("revise", "eval_gate")
        graph.add_edge("promote", END)
        graph.add_edge("reject", END)
        return graph.compile()

    def run_cycle(self, traces: list[dict]) -> dict:
        """Given — orchestrates the whole thing: batch analytics and
        mining run once over every trace; the graph runs once PER newly
        mined golden, because the repair loop is a per-item concern."""
        metrics = AnalyticsEngine.compute(traces)
        Dashboard.build(metrics, DASHBOARD_FILE)

        failing = QAMiner.mine(traces)
        new_goldens = GoldenBuilder.promote(failing)
        if not new_goldens:
            return {"metrics": metrics, "failing_traces": failing, "new_goldens": [], "results": [], "outcome": "no_new_goldens"}

        results = []
        for golden in new_goldens:
            customer = CUSTOMERS_BY_ID[golden["customer_id"]]
            final_state = self.graph.invoke({"golden": golden, "customer": customer, "repair_attempted": False})
            results.append({
                "golden_id": golden["golden_id"],
                "customer_id": customer["customer_id"],
                "outcome": final_state["outcome"],
                "article_cited": final_state["article"]["article_id"] if final_state["article"] else None,
                "response_text": final_state["response_text"],
                "checks": {name: result["passed"] for name, result in final_state["checks"].items()},
                "repaired": final_state.get("repair_attempted", False),
            })

        run_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "goldens_processed": len(new_goldens),
            "promoted": sum(1 for r in results if r["outcome"] == "promoted"),
            "rejected": sum(1 for r in results if r["outcome"] == "rejected"),
            "results": results,
        }
        history = json.load(open(EVAL_RUNS_FILE, encoding="utf-8")) if EVAL_RUNS_FILE.exists() else []
        history.append(run_record)
        with open(EVAL_RUNS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        return {"metrics": metrics, "failing_traces": failing, "new_goldens": new_goldens, "results": results, "outcome": "cycle_complete"}


def demo_repair_loop() -> None:
    """Given — none of the 4 real goldens are guaranteed to trip the
    repair loop (a correct implementation clears the deterministic checks
    on the first try; only relevance_judge could fail one, and that's not
    what the loop exists to fix). This exercises revise_node
    deterministically instead, same treatment Day7 gave its brand-safety
    loop with a hand-crafted adversarial string."""
    print("\n=== Demo: forcing the repair loop with a hand-crafted bad draft ===")
    bad_customer = {"customer_id": "DEMO", "name": "Demo Customer", "policy_type": "auto", "segment": "standard",
                     "pending_question": "will my claim be approved"}
    state: CycleState = {
        "customer": bad_customer,
        "article": KB_ARTICLES_BY_ID["KB-02"],
        "response_text": (
            "Great news — this is a guaranteed payout under your liability coverage, no questions asked! "
            f"{REQUIRED_DISCLOSURE}"
        ),
        "repair_attempted": False,
    }
    state.update(eval_gate_node(state))
    print(f"  First draft passed={state['passed']} -> no_banned_phrase: {state['checks']['no_banned_phrase']}")
    if not state["passed"]:
        state.update(revise_node(state))
        print(f"  Repaired: \"{state['response_text']}\"")
        state.update(eval_gate_node(state))
        print(f"  Second judgment passed={state['passed']}")
    outcome = "promoted" if state["passed"] else "rejected"
    print(f"  Outcome: {outcome} (repair_attempted={state['repair_attempted']})")


def capstone_selfcheck(command_center: ImprovementCommandCenter) -> bool:
    """Given — the grading harness. Re-derives everything from
    claim_traces.json directly rather than trusting goldens.json/
    capstone_eval_runs.json's accumulated state, so it gives the same
    verdict whether this is the first time this file has ever run or the
    fiftieth. Hard-asserts only DETERMINISTIC behavior — relevance_judge
    is reported, never graded, since it's a live model's opinion, not a
    fact about your code. This is the day's own "eval-gated update" idea,
    pointed at your submission instead of a personalisation engine."""
    print("\n=== Capstone self-check ===")
    scorecard = []

    metrics = AnalyticsEngine.compute(CLAIM_TRACES)
    vbpt = metrics.get("volume_by_policy_type", {})
    ok = metrics.get("total_traces") == 10 and vbpt.get("auto") == 5 and vbpt.get("home") == 3 and vbpt.get("health") == 2
    scorecard.append(("AnalyticsEngine.compute totals correct (10 traces; auto=5/home=3/health=2)", ok))

    failing = QAMiner.mine(CLAIM_TRACES)
    failing_ids = {f["customer_id"] for f in failing}
    scorecard.append(("QAMiner finds exactly the 4 expected customers", failing_ids == EXPECTED_FAILING_CUSTOMER_IDS))

    for customer_id in sorted(EXPECTED_FAILING_CUSTOMER_IDS):
        customer = CUSTOMERS_BY_ID[customer_id]
        state = command_center.graph.invoke({
            "golden": {"customer_id": customer_id}, "customer": customer, "repair_attempted": False,
        })
        output = {
            "article_cited": state["article"]["article_id"] if state["article"] else None,
            "response_text": state["response_text"],
        }
        deterministic = run_checks(output, customer, deterministic_only=True)
        all_pass = all(result["passed"] for result in deterministic.values())
        scorecard.append((f"{customer_id}: fresh response clears all deterministic checks", all_pass))

        judge = run_checks(output, customer, deterministic_only=False).get("relevance_judge")
        if judge:
            print(f"    (informational, not graded) {customer_id} relevance_judge: "
                  f"{'pass' if judge['passed'] else 'fail'} — {judge['detail']}")

    passed = sum(1 for _, ok in scorecard if ok)
    for label, ok in scorecard:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print(f"\n  {passed}/{len(scorecard)} checks passed.")
    return passed == len(scorecard)


if __name__ == "__main__":
    print(f"=== Capstone: Insurance Improvement Loop — {len(CLAIM_TRACES)} historical traces, {len(CUSTOMERS)} customers ===")

    center = ImprovementCommandCenter()
    cycle = center.run_cycle(CLAIM_TRACES)

    print(f"\n--- Analytics ({cycle['metrics']['total_traces']} traces) ---")
    print(f"  Volume by policy type: {cycle['metrics']['volume_by_policy_type']}")
    print(f"  Top cited articles: {cycle['metrics']['top_cited_articles']}")
    print(f"  Dashboard written -> {DASHBOARD_FILE.name}")

    print(f"\n--- Mining: {len(cycle['failing_traces'])} of {len(CLAIM_TRACES)} traces failed QA ---")
    for f in cycle["failing_traces"]:
        print(f"  {f['trace_id']} ({f['customer_id']}): {f['failed_checks']}")

    if cycle["outcome"] == "no_new_goldens":
        print("\n  No NEW goldens this cycle (all already captured in a prior run) — skipping the graph.")
    else:
        print(f"\n--- Improvement cycle: {len(cycle['new_goldens'])} new golden(s) run through the graph ---")
        for result in cycle["results"]:
            print(f"  {result['customer_id']} ({result['golden_id']}): {result['outcome'].upper()} "
                  f"via {result['article_cited']}, repaired={result['repaired']}")
            print(f"    \"{result['response_text']}\"")
            print(f"    checks: {result['checks']}")

    demo_repair_loop()

    ok = capstone_selfcheck(center)
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED — see scorecard above'}")

# Expected (hand-verified against claim_traces.json / insurance_customers.json):
# AnalyticsEngine: 10 traces, volume_by_policy_type = {auto: 5, home: 3, health: 2}
# (CUST-C01/C04/C07 x their trace counts = 2+2+1=5 auto; C02/C05/C08=1+1+1=3 home;
# C03/C06=1+1=2 health). Mining is fully deterministic (judge excluded) and
# finds EXACTLY 5 failing traces -> 4 unique customers: CUST-C01 (TR-I09, cited
# a home article on an auto policy), CUST-C03 (TR-I03, cited an auto article on
# a health policy), CUST-C04 (TR-I04/TR-I10, "automatically approved" /
# "guaranteed payout"), CUST-C05 (TR-I05, missing disclosure). This is a fixed
# set every run, not model-dependent — capstone_selfcheck hard-asserts it.
# For each of those 4 customers, a CORRECT response_agent_node retrieves a
# policy_type-appropriate article (impossible to get wrong given
# KnowledgeBase's hard filter) and a CORRECT draft_response includes the
# disclosure and avoids all 4 banned phrases — so all 3 deterministic checks
# should pass for all 4, deterministically, every run. relevance_judge is a
# REAL model call and is reported but never hard-graded — don't be alarmed by
# an occasional judge disagreement on an otherwise-correct response.
