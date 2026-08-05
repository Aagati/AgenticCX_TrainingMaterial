"""
Capstone: Insurance - Prove the Loop Works Before a Real Customer Sees It (STARTER).

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

THREE THINGS ADDED BEYOND THE ORIGINAL SCOPE: (1) Lab-3's staleness idea,
actually fused rather than named-dropped — KnowledgeBase carries
status/last_updated, excludes deprecated articles at the source, and a
`kb_article_not_stale` check backstops it, on a THIRD registry axis
(`mineable`) separate from `deterministic` — staleness is a fact about
today, not about the moment a historical trace was sent, so QAMiner never
mines by it. (2) the dashboard now reads capstone_eval_runs.json back and
plots a real trend across cycles, instead of only ever showing the current
cycle's snapshot. (3) a failed gate no longer dead-ends at "rejected" — the
graph routes to a route_to_human node that returns a safe holding message,
because a failing draft should produce a handoff, not silence.

You'll build:
  1. Four deterministic QA checks + the LLM-judge check (the registry
     itself, with its deterministic/mineable split, is given).
  2. AnalyticsEngine.compute — the batch metrics feeding the dashboard.
  3. QAMiner.mine — deterministic-and-mineable-only mining over
     claim_traces.json.
  4. response_agent_node (+ draft_response) — the personalisation +
     grounded-drafting agent, using the GIVEN KnowledgeBase.
  5. eval_gate_node — full-registry judgment on a candidate response.
  6. ImprovementCommandCenter._build_graph — wire the 6 nodes into the
     one-cycle graph described above (the new edge: a rejected gate hands
     off to route_to_human instead of dead-ending).
"""

import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
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

# Lab-3's mechanic, ported: a policy article can be old but still safe to
# cite ("stale" — soft, gets a mention in the response) or explicitly
# retired ("deprecated" — hard, must never reach a customer). NOW is fixed,
# same convention as Lab-3, so a re-run doesn't silently reclassify articles
# because the wall clock moved.
STALENESS_WINDOW_DAYS = 365
NOW = date(2026, 8, 4)

client = Anthropic()

INK = "#0b0b0b"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
CATEGORICAL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a"}
DIVERGING = {"negative": "#e34948", "neutral": "#c3c2b7", "positive": "#2a78d6"}

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
# as Lab-2, extended with TWO independent flags: `deterministic` (no model
# call — false only for relevance_judge) and `mineable` (is this fact
# stable enough to grade a HISTORICAL trace by?). Staleness isn't mineable:
# an article current when a trace was sent can be stale today, so grading
# an old trace by today's staleness window would apply a rule that didn't
# exist yet. Deterministic-but-not-mineable checks still gate live output
# — QAMiner just doesn't run them over the past.
# ---------------------------------------------------------------------------

_CHECK_REGISTRY: dict[str, dict] = {}


def register_check(name: str, deterministic: bool = True, mineable: bool = True):
    def decorator(fn):
        _CHECK_REGISTRY[name] = {"fn": fn, "deterministic": deterministic, "mineable": mineable}
        return fn
    return decorator


def run_checks(output: dict, customer: dict, deterministic_only: bool = False, mineable_only: bool = False) -> dict:
    """Given — output is {"article_cited": str|None, "response_text": str}."""
    results = {}
    for name, entry in _CHECK_REGISTRY.items():
        if deterministic_only and not entry["deterministic"]:
            continue
        if mineable_only and not entry["mineable"]:
            continue
        results[name] = entry["fn"](output, customer)
    return results


@register_check("policy_type_respected")
def check_policy_type_respected(output: dict, customer: dict) -> dict:
    """
    TODO 1a: If output["article_cited"] is None, pass trivially. Else look
    up the article via KB_ARTICLES_BY_ID and fail unless
    customer["policy_type"] is in that article's "policy_type" list.
    detail should name the article and policy_type on failure, "ok" on pass.
    """
    raise NotImplementedError


@register_check("no_banned_phrase")
def check_no_banned_phrase(output: dict, customer: dict) -> dict:
    """
    TODO 1b: Case-insensitive substring check of output["response_text"]
    against BANNED_PHRASES. Fail (listing which phrase(s) hit) if any are
    present, else pass.
    """
    raise NotImplementedError


@register_check("required_disclosure_present")
def check_required_disclosure(output: dict, customer: dict) -> dict:
    """
    TODO 1c: Fail unless REQUIRED_DISCLOSURE appears verbatim
    (case-insensitive is fine) in output["response_text"].
    """
    raise NotImplementedError


@register_check("kb_article_not_stale", mineable=False)
def check_kb_article_not_stale(output: dict, customer: dict) -> dict:
    """
    TODO 1d: If output["article_cited"] is None, pass trivially. Else look
    up the article via KB_ARTICLES_BY_ID and fail if its "status" ==
    "deprecated" (detail should name the article), else pass ("ok"). This
    is a BACKSTOP, not the primary defense — KnowledgeBase.retrieve()
    below already excludes deprecated articles before scoring, so on live
    output this should always pass; it exists to catch a deprecated
    citation that reached drafting some other way, same role
    eligibility_respected plays for PersonalisationEngine in Lab-2.
    Registered `mineable=False` (given) — staleness is a fact about TODAY,
    not about the moment a historical trace was sent, so QAMiner (TODO 3)
    is built to never grade the past by it.
    """
    raise NotImplementedError


def flag_staleness(articles: list[dict], now: date = NOW) -> list[dict]:
    """Given — Lab-3's two-signal staleness judgment, ported verbatim:
    an explicit status flag (hard) and last_updated age (soft)."""
    flagged = []
    for article in articles:
        if article["status"] == "deprecated":
            flag = "deprecated"
        elif (now - date.fromisoformat(article["last_updated"])).days > STALENESS_WINDOW_DAYS:
            flag = "stale"
        else:
            flag = None
        flagged.append({**article, "staleness_flag": flag})
    return flagged


@register_check("relevance_judge", deterministic=False)
def check_relevance_judge(output: dict, customer: dict) -> dict:
    """
    TODO 1e: The one subjective check — real haiku call, forced tool use.
    If output["article_cited"] is None, pass trivially. Else: system
    prompt explains this is a QA reviewer judging whether the response is
    well-grounded and actually answers the customer's question (not
    compliance — the other checks own that); user content = the
    customer's pending_question, policy_type, the cited article's title,
    and the response text. Force a tool call on
    RelevanceJudgment.model_json_schema(), parse it, return
    {"passed": result.passed, "detail": result.reason}.
    """
    raise NotImplementedError


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
        """Given. Excludes deprecated articles before scoring even starts
        — the primary defense against citing retired content (Lab-3's
        #1-slot guarantee, generalized to the whole candidate pool since
        this dataset has no like-for-like replacement to substitute in).
        kb_article_not_stale (TODO 1d) is the backstop for anything that
        reaches drafting some other way."""
        query_lower = query.lower()
        candidates = [a for a in KB_ARTICLES if policy_type in a["policy_type"] and a.get("status") != "deprecated"]
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
        """
        TODO 2: Return {"total_traces": len(traces), "volume_by_policy_type":
        a dict counting each trace's customer's policy_type (look the
        customer up via CUSTOMERS_BY_ID[trace["customer_id"]]),
        "top_cited_articles": Counter(trace["article_cited"] for trace in
        traces).most_common(5)}.
        """
        raise NotImplementedError


class Dashboard:
    """Given — same chart chrome as Lab-1's Dashboard. Top row: the
    original two trace-analytics panels. Bottom row: reads
    capstone_eval_runs.json back and plots a real cross-cycle trend,
    instead of only ever showing the current cycle's snapshot."""

    @staticmethod
    def build(metrics: dict, eval_history: list[dict], out_path: Path) -> None:
        fig, axes = plt.subplots(2, 2, figsize=(11, 9), facecolor=SURFACE)
        for ax in axes.flat:
            ax.set_facecolor(SURFACE)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(INK_MUTED)
            ax.tick_params(colors=INK_MUTED, labelsize=9)
            ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
            ax.set_axisbelow(True)

        ax = axes[0, 0]
        policy_colors = {"auto": CATEGORICAL["blue"], "home": CATEGORICAL["orange"], "health": CATEGORICAL["aqua"]}
        types = list(metrics["volume_by_policy_type"].keys())
        bars = ax.bar(types, [metrics["volume_by_policy_type"][t] for t in types],
                       color=[policy_colors.get(t, INK_MUTED) for t in types], width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Claim volume by policy type", color=INK, fontsize=11, loc="left", fontweight="bold")

        ax = axes[0, 1]
        top = metrics["top_cited_articles"]
        labels = [article_id for article_id, _ in top]
        counts = [count for _, count in top]
        bars = ax.barh(labels, counts, color=CATEGORICAL["blue"], height=0.6, zorder=3)
        ax.invert_yaxis()
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Most-cited articles", color=INK, fontsize=11, loc="left", fontweight="bold")

        # bottom row: cross-cycle trend from capstone_eval_runs.json — every
        # cycle that processed at least one new golden appended a record;
        # skipped cycles (no_new_goldens) simply don't add a point.
        cycle_idx = list(range(1, len(eval_history) + 1))
        pass_rate_series = [
            round(r["promoted"] / r["goldens_processed"], 3) if r["goldens_processed"] else 0.0
            for r in eval_history
        ]
        handoff_rate_series = [
            round(r["routed_to_human"] / r["goldens_processed"], 3) if r["goldens_processed"] else 0.0
            for r in eval_history
        ]

        ax = axes[1, 0]
        if len(eval_history) >= 2:
            ax.plot(cycle_idx, pass_rate_series, color=CATEGORICAL["blue"], linewidth=2, marker="o", markersize=5, zorder=3)
        elif eval_history:
            ax.plot(cycle_idx, pass_rate_series, color=CATEGORICAL["blue"], marker="o", markersize=6, zorder=3)
            ax.set_xlim(0, 2)
            ax.text(0.5, 0.15, "needs 2+ cycles for a line", transform=ax.transAxes, ha="center",
                     color=INK_MUTED, fontsize=8)
        else:
            ax.text(0.5, 0.5, "no cycles logged yet", transform=ax.transAxes, ha="center", va="center",
                     color=INK_MUTED, fontsize=9)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xticks(cycle_idx)
        ax.set_title(f"Golden pass rate across cycles (n={len(eval_history)})", color=INK, fontsize=11, loc="left", fontweight="bold")

        ax = axes[1, 1]
        if len(eval_history) >= 2:
            ax.plot(cycle_idx, handoff_rate_series, color=DIVERGING["negative"], linewidth=2, marker="o", markersize=5, zorder=3)
        elif eval_history:
            ax.plot(cycle_idx, handoff_rate_series, color=DIVERGING["negative"], marker="o", markersize=6, zorder=3)
            ax.set_xlim(0, 2)
            ax.text(0.5, 0.15, "needs 2+ cycles for a line", transform=ax.transAxes, ha="center",
                     color=INK_MUTED, fontsize=8)
        else:
            ax.text(0.5, 0.5, "no cycles logged yet", transform=ax.transAxes, ha="center", va="center",
                     color=INK_MUTED, fontsize=9)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xticks(cycle_idx)
        ax.set_title(f"Human-handoff rate across cycles (n={len(eval_history)})", color=INK, fontsize=11, loc="left", fontweight="bold")

        fig.suptitle("Insurance Improvement Loop — Trace Analytics & Gate Trend", color=INK, fontsize=13, fontweight="bold", x=0.02, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_path, dpi=130, facecolor=SURFACE)
        plt.close(fig)


# ---------------------------------------------------------------------------
# Lab-2 content: mining, goldens, the drafting agent, the eval gate
# ---------------------------------------------------------------------------

class QAMiner:
    @staticmethod
    def mine(traces: list[dict]) -> list[dict]:
        """
        TODO 3: For each trace, look up its customer via CUSTOMERS_BY_ID,
        build output = {"article_cited": trace["article_cited"],
        "response_text": trace["response_text"]}, and run_checks(output,
        customer, deterministic_only=True, mineable_only=True) — BOTH
        filters, not just deterministic: this is mining, not gating, and
        kb_article_not_stale is deterministic but NOT mineable (see its
        TODO 1d docstring and the module docstring for why). If any
        check's "passed" is False, append {"trace_id":..., "customer_id":
        ..., "failed_checks": {name: detail for every FAILING check}}.
        Return the list of failing records.
        """
        raise NotImplementedError


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
    """
    TODO 4a: If `article` is None, return a short "I don't have a specific
    article yet — connecting you with a specialist" sentence that still
    ends with REQUIRED_DISCLOSURE, no model call. Else real sonnet call:
    tone = "white-glove and proactive" if customer["segment"] == "premium"
    else "friendly and direct" — this IS the personalisation axis in this
    capstone (Lab-2's segment-driven tone, not a new mechanic). If
    article.get("staleness_flag") == "stale", add one more instruction to
    the system prompt: briefly note the customer may want to confirm
    current terms (soft — never blocks, just gets mentioned; "deprecated"
    articles never reach this function at all, see KnowledgeBase.retrieve
    and TODO 1d). system prompt: answer using ONLY the provided article,
    never invent a coverage detail, include REQUIRED_DISCLOSURE verbatim
    as the final sentence, never use an absolute claim (guaranteed payout,
    automatic approval). user content: customer first name + policy_type +
    their pending_question + the article's title/body.
    client.messages.create(model=MODEL_DRAFT, max_tokens=300, system=...,
    messages=[{"role": "user", "content": ...}]) — return the text,
    stripped.
    """
    raise NotImplementedError


def response_agent_node(state: CycleState) -> dict:
    """
    TODO 4b: customer = state["customer"]. Call KnowledgeBase.retrieve
    with customer's pending_question and policy_type (top_k=1) — take the
    first result, or None if the list is empty. If you got a result, run
    it through flag_staleness(...) (given, above) so draft_response can
    see staleness_flag — article = flag_staleness(articles)[0] if
    articles else None. Call draft_response(customer, article). Return
    {"article": article, "response_text": <the draft>}.
    """
    raise NotImplementedError


def eval_gate_node(state: CycleState) -> dict:
    """
    TODO 5: Build output = {"article_cited": state["article"]'s id or None,
    "response_text": state["response_text"]}. Run run_checks(output,
    state["customer"], deterministic_only=False) — the FULL registry,
    judge included, this is gating a live candidate. passed = True only if
    every check passed. Return {"checks": checks, "passed": passed}.
    """
    raise NotImplementedError


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


def route_to_human_node(state: CycleState) -> dict:
    """Given — a failed repair isn't a dead end, it's a handoff, same
    instinct as Lab-3's KnowledgeBase falling back to 'connecting you
    with a specialist' when nothing grounds an answer. The customer still
    gets a safe, disclosure-carrying holding message; the ORIGINAL
    non-compliant draft never ships, which is the property that actually
    matters here."""
    customer = state["customer"]
    first_name = customer["name"].split()[0] if "name" in customer else "there"
    handoff_text = (
        f"Hi {first_name}, I want to make sure you get this exactly right, so I'm looping in a specialist "
        f"to follow up with you directly. {REQUIRED_DISCLOSURE}"
    )
    return {"outcome": "routed_to_human", "response_text": handoff_text}


def reject_node(state: CycleState) -> dict:
    """Given — kept distinct from route_to_human: 'rejected' is the
    engineering verdict logged for this golden (the candidate response
    failed the gate twice), 'routed_to_human' is what the customer
    actually receives instead of the failing draft. reject_node always
    hands off to route_to_human next in the graph below (TODO 6) —
    nothing ever ships a failing response."""
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
        """
        TODO 6: Build a StateGraph(CycleState) with 6 nodes registered:
        "response_agent" -> response_agent_node, "eval_gate" ->
        eval_gate_node, "revise" -> revise_node, "promote" -> promote_node,
        "reject" -> reject_node, "route_to_human" -> route_to_human_node.
        Entry point: "response_agent". Topology: response_agent ->
        eval_gate (unconditional); eval_gate -> conditional via
        _route_after_gate, mapping "promote"/"revise"/"reject" to the
        like-named nodes; revise -> eval_gate (the one cycle in this
        graph — everything else is a DAG); promote -> END; reject ->
        route_to_human (NOT straight to END — a rejected gate still needs
        to produce something the customer sees); route_to_human -> END.
        Return graph.compile().
        """
        raise NotImplementedError

    def run_cycle(self, traces: list[dict]) -> dict:
        """Given — orchestrates the whole thing: batch analytics and
        mining run once over every trace; the graph runs once PER newly
        mined golden, because the repair loop is a per-item concern. The
        dashboard is built LAST, after this cycle's eval-run record (if
        any) is on disk — so its trend panel includes the run that just
        happened, not just every run before it."""
        metrics = AnalyticsEngine.compute(traces)

        failing = QAMiner.mine(traces)
        new_goldens = GoldenBuilder.promote(failing)
        if not new_goldens:
            eval_history = json.load(open(EVAL_RUNS_FILE, encoding="utf-8")) if EVAL_RUNS_FILE.exists() else []
            Dashboard.build(metrics, eval_history, DASHBOARD_FILE)
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
            "routed_to_human": sum(1 for r in results if r["outcome"] == "routed_to_human"),
            "results": results,
        }
        eval_history = json.load(open(EVAL_RUNS_FILE, encoding="utf-8")) if EVAL_RUNS_FILE.exists() else []
        eval_history.append(run_record)
        with open(EVAL_RUNS_FILE, "w", encoding="utf-8") as f:
            json.dump(eval_history, f, ensure_ascii=False, indent=2)

        Dashboard.build(metrics, eval_history, DASHBOARD_FILE)

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


def demo_staleness_guard() -> None:
    """Given — KnowledgeBase.retrieve() excludes deprecated articles
    (KB-01) at the source, and no real customer's pending_question routes
    to it anyway, so the live pipeline never exercises
    kb_article_not_stale failing. This proves the check still catches a
    deprecated citation if one ever reached drafting some other way —
    same hand-crafted-adversarial-input treatment demo_repair_loop gives
    the repair path — and confirms live retrieval genuinely can't produce
    it for the topic KB-01 covers."""
    print("\n=== Demo: kb_article_not_stale catching a deprecated citation ===")
    bypassed_output = {"article_cited": "KB-01", "response_text": "irrelevant for this check"}
    result = check_kb_article_not_stale(bypassed_output, {"customer_id": "DEMO2"})
    print(f"  Citing deprecated KB-01 directly: passed={result['passed']} -> {result['detail']}")

    live = KnowledgeBase.retrieve("collision damage after an accident", "auto", top_k=1)
    print(f"  Live retrieve() for a collision query never surfaces it: {[a['article_id'] for a in live]}")

    stale_article = flag_staleness([KB_ARTICLES_BY_ID["KB-08"]])[0]
    print(f"  KB-08 last_updated=2024-05-01 vs NOW={NOW}: staleness_flag={stale_article['staleness_flag']!r} (soft — noted in drafting, not blocked)")


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

    # None of the 4 real goldens exercise the deprecated-article guard or the
    # human-handoff path (by design — see module docstring), so without these
    # two checks a broken KnowledgeBase.retrieve() or a deleted route_to_human
    # node would score 100% above and still be silently wrong.
    never_deprecated = all(
        a["article_id"] != "KB-01" for a in KnowledgeBase.retrieve("collision damage after an accident", "auto", top_k=10)
    )
    scorecard.append(("KnowledgeBase.retrieve never surfaces the deprecated KB-01", never_deprecated))

    graph_node_names = set(command_center.graph.get_graph().nodes)
    scorecard.append((
        "graph wires reject -> route_to_human (not a dead end)",
        {"reject", "route_to_human"} <= graph_node_names,
    ))

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
    demo_staleness_guard()

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
#
# Staleness: KB-01 is status="deprecated" and cited by no customer's
# pending_question, so it never surfaces through retrieve() (excluded at the
# source, TODO 1d's job is the backstop) and kb_article_not_stale passes
# trivially for all live traffic — demo_staleness_guard() is what actually
# exercises the check, by citing KB-01 directly rather than through
# retrieval. QAMiner does NOT run kb_article_not_stale (mineable=False) —
# staleness is a NOW-relative fact, so grading a trace sent on 2026-07-10 by
# 2026-08-04's staleness window would be judging it by a rule that didn't
# apply yet; the 5-failing-traces/4-customers count above is unaffected by
# staleness entirely. KB-08 is status="active" but last_updated="2024-05-01"
# (soft "stale", >365 days before NOW) — never blocks anything, just adds a
# one-line "may want to confirm current terms" note when drafting cites it.
#
# reject -> route_to_human: a golden that fails the gate twice no longer
# just stops at "rejected" — the graph (TODO 6) hands off to
# route_to_human_node, which returns a safe, disclosure-carrying holding
# message instead of ever shipping the failing draft. None of the 4 real
# goldens are expected to reach this path on a correct implementation (same
# reasoning as the repair loop above); it exists for the case a repair
# attempt genuinely can't fix, not as something this run should hit.
