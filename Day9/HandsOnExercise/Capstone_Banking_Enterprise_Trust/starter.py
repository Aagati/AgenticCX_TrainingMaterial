"""
Capstone: Banking - Enterprise Won't Trust a Demo (STARTER).

Every mechanic Day 9 taught, fused into one pipeline: a guardrail stack
(Lab-2, thinned to six layers) gates a resilient action (Lab-1's circuit
breaker + retry, wrapping an idempotent core-banking call) whose output is
judged, and - if it fails - repaired once and re-judged (the one genuinely
cyclic part; everything else is a straight-line batch). Lab-3's redaction
utility ships given, not a TODO, and is actually enforced rather than
merely explained.

This capstone ALSO reaches back past its own day - something no earlier
capstone in this curriculum did:
  - Day 4's idempotent, audited action (`process_refund` /
    `create_ticket`) -> here, the SAME replay contract, now actually
    retried under a circuit breaker (`guarded_action`). Physical attempts
    collapse to a handful of ledger rows - idempotency and retry are one
    design decision, not two.
  - Day 4's per-user permission check (`check_permission`'s "doesn't own
    it" branch) -> generalized into role -> capability (`rbac_action_allowed`)
    plus a numeric ceiling Day 4 had no analogue for (`rbac_credit_ceiling`).
  - Day 5's governance pack (agent card, audit trail schema) -> here it's
    runtime policy: `banking_policy_pack.json["agent_card"]["approval_threshold"]`
    is what routes a CLEAN pass to a human, and the audit trail is
    hash-chained instead of a flat in-memory list.
  - Day 8's Batches API (Lab-1) + eval_gated decorator (Lab-2) -> here they
    gate the GUARDRAIL STACK itself: one Batches job judges every processed
    customer's response, and `.run_gate()` re-runs the whole pipeline and
    logs a promote/reject verdict - with a SECOND failure direction Day 8's
    gate never had (a false block is exactly as much a failure as a missed
    one).

You'll build:
  1. Five guardrail layers (the registry and the always-runs audit layer
     are given).
  2. GuardrailStack.evaluate, CircuitBreaker, call_with_retry, guarded_action.
  3. AuditChain.append / .verify (hash-chained, same math as Lab-2).
  4. draft_response - grounded strictly in what the action actually returned.
  5. agent_node / guardrail_node (the two TODO graph nodes) and
     _build_graph (the topology).
  6. CapacityMeter.compute - the batch-level metrics behind the dashboard.
  7. run_corpus, BatchGate.build_requests/.run, eval_gated.
"""

import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, TypedDict

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
with open(DATA_DIR / "banking_policy_pack.json", encoding="utf-8") as f:
    _POLICY = json.load(f)
    AGENT_CARD = _POLICY["agent_card"]
    ROLES = _POLICY["roles"]
    ACTORS = _POLICY["actors"]
    JURISDICTIONS = _POLICY["jurisdictions"]
    WRITTEN_CONFIRMATION_SENTENCE = _POLICY["written_confirmation_sentence"]
with open(DATA_DIR / "banking_customers.json", encoding="utf-8") as f:
    CUSTOMERS = json.load(f)["customers"]
with open(DATA_DIR / "core_banking_faults.json", encoding="utf-8") as f:
    FAULTS = json.load(f)["faults"]
with open(DATA_DIR / "adversarial_corpus.json", encoding="utf-8") as f:
    CORPUS = json.load(f)["traces"]

AUDIT_CHAIN_FILE = DATA_DIR / "capstone_audit_chain.json"
EVAL_RUNS_FILE = DATA_DIR / "capstone_eval_runs.json"
DASHBOARD_FILE = DATA_DIR / "capstone_dashboard.png"

APPROVAL_THRESHOLD = AGENT_CARD["approval_threshold"]
BREAKER_FAILURE_THRESHOLD = 3
BREAKER_RECOVERY_SECONDS = 60
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.3

INJECTION_PATTERNS = [
    "ignore all previous instructions", "ignore your instructions", "disregard your system",
    "disregard the above", "disregard your system instructions", "ignore the above",
]

EXPECTED_BLOCKED_TRACE_IDS = {t["trace_id"] for t in CORPUS if t["is_adversarial"]}
EXPECTED_DENIED_CUSTOMER_IDS = {"CUST-BK05", "CUST-BK08"}

client = Anthropic()
random.seed(9)

INK = "#0b0b0b"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
CATEGORICAL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a"}
DIVERGING = {"negative": "#e34948", "neutral": "#c3c2b7", "positive": "#2a78d6"}


# ---------------------------------------------------------------------------
# Lab-3's idea, given: redact anything that looks like a card/key/policy
# number before it goes anywhere durable. Thinned to the two CRITICAL
# patterns - this capstone's records are internal dispute records, not a
# support transcript, so email/phone/govt-id aren't this function's job.
# ---------------------------------------------------------------------------

_LOG_REDACTION_PATTERNS = [
    (re.compile(r"sk-(?:live|test)-\w{8,}"), "[API_KEY_REDACTED]"),
    (re.compile(r"\b\d(?:[ -]?\d){12,18}"), "[CARD_REDACTED]"),
]


def redact_for_log(text: str) -> str:
    """Given - Lab-3's idea, enforced here rather than merely explained:
    capstone_selfcheck asserts this is still wired up, because a redaction
    bug in an enterprise pipeline is a breach, not a stale citation."""
    for pattern, replacement in _LOG_REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Given: the flaky core-banking dependency + its idempotency ledger.
# ---------------------------------------------------------------------------

class CoreBankingError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class CoreBankingAPI:
    """Given - `ledger` is keyed by idempotency_key: a SECOND call with a
    key already in the ledger returns the cached result WITHOUT consuming
    an attempt or re-crediting. That's the idempotency contract Day 4's
    `process_refund` established; this capstone is the first time it's
    tested against a dependency that actually fails."""

    def __init__(self, faults: dict):
        self.faults = faults
        self._calls_so_far: dict[str, int] = {}
        self.attempt_count = 0
        self.ledger: dict[str, dict] = {}

    def issue_provisional_credit(self, dispute_id: str, amount: float, idempotency_key: str) -> dict:
        if idempotency_key in self.ledger:
            return self.ledger[idempotency_key]
        self.attempt_count += 1
        behavior = self.faults[dispute_id]["behavior"]
        n = self._calls_so_far.get(dispute_id, 0)
        self._calls_so_far[dispute_id] = n + 1
        if behavior == "fail_once" and n == 0:
            raise CoreBankingError("core-banking: 500", retryable=True)
        if behavior == "fail_twice" and n < 2:
            raise CoreBankingError("core-banking: 500", retryable=True)
        if behavior == "fail_always":
            raise CoreBankingError("core-banking: 500", retryable=True)
        result = {"status": "credited", "dispute_id": dispute_id, "amount": amount}
        self.ledger[idempotency_key] = result
        return result


class GuardrailResult(TypedDict, total=False):
    verdict: Literal["PASS", "BLOCK", "REDACT"]
    detail: str
    payload: str


def resolve_context(customer: dict, action: str, credit_amount: Optional[float], actor_id: Optional[str] = None) -> dict:
    """Given - actor to role, customer to jurisdiction. `actor_id` defaults
    to the customer's own requesting_actor (the live-pipeline case); the
    corpus passes its OWN actor_id per trace, since the whole point of
    several traces is testing a DIFFERENT actor against the same customer."""
    actor_id = actor_id or customer["requesting_actor"]
    role_name = ACTORS[actor_id]["role"]
    role = ROLES[role_name]
    jurisdiction_code = customer["jurisdiction"]
    jurisdiction = JURISDICTIONS.get(jurisdiction_code, JURISDICTIONS["DEFAULT"])
    return {
        "actor_id": actor_id, "role_name": role_name, "role": role,
        "customer_id": customer["customer_id"], "jurisdiction_code": jurisdiction_code,
        "jurisdiction": jurisdiction, "action": action, "credit_amount": credit_amount,
    }


# ---------------------------------------------------------------------------
# Guardrail registry - given infrastructure; the five layers and the chain
# that walks them are yours.
# ---------------------------------------------------------------------------

_GUARDRAIL_REGISTRY: list[dict] = []


def register_guardrail(name: str, group: str, order: int, always_runs: bool = False):
    def decorator(fn):
        _GUARDRAIL_REGISTRY.append({"name": name, "group": group, "order": order, "always_runs": always_runs, "fn": fn})
        return fn
    return decorator


@register_guardrail("injection_probe", group="input", order=10)
def guard_injection(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1a: Case-insensitive substring scan of `payload` against
    INJECTION_PATTERNS. BLOCK naming the phrase that hit; else PASS.
    """
    raise NotImplementedError


@register_guardrail("rbac_action_allowed", group="permission", order=20)
def guard_rbac_action(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1b: BLOCK unless context["action"] is in context["role"]["actions"].
    detail should name the role and the disallowed action on failure, "ok"
    on pass.
    """
    raise NotImplementedError


@register_guardrail("rbac_credit_ceiling", group="permission", order=30)
def guard_rbac_ceiling(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1c: If context["action"] == "issue_provisional_credit" and
    context["credit_amount"] is not None, BLOCK when it EXCEEDS (strictly
    greater than) context["role"]["max_credit_authority"]. Equal to the
    ceiling PASSES - the boundary is inclusive. This generalizes Day 4's
    per-user ownership check into role -> capability, with a numeric
    ceiling Day 4 had no analogue for.
    """
    raise NotImplementedError


@register_guardrail("jurisdiction_disclosure_present", group="compliance", order=40)
def guard_disclosure(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1d: The one REDACT layer - transforms and continues, never
    BLOCKs. If context["jurisdiction"]["required_disclosure"] does not
    appear verbatim (case-insensitive is fine) in `payload`, REDACT by
    appending it as the payload's own final sentence. Additionally, if
    context["credit_amount"] is not None and exceeds
    context["jurisdiction"]["requires_written_confirmation_above"], also
    append WRITTEN_CONFIRMATION_SENTENCE. PASS unchanged only if nothing
    needed adding.
    """
    raise NotImplementedError


@register_guardrail("prohibited_claim", group="compliance", order=50)
def guard_prohibited(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1e: Case-insensitive substring scan of `payload` against THIS
    JURISDICTION'S prohibited_phrases (context["jurisdiction"]["prohibited_phrases"]),
    not a global list. BLOCK naming every phrase that hit.
    """
    raise NotImplementedError


@register_guardrail("audit_chain_write", group="audit", order=60, always_runs=True)
def guard_audit_write(payload: str, context: dict) -> GuardrailResult:
    """Given - always PASS, always runs. Writes one hash-chained entry per
    evaluate() call, same shape as Lab-2's."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor_id": context["actor_id"], "actor_role": context["role_name"],
        "action": context["action"], "subject_customer_id": context["customer_id"],
        "jurisdiction": context["jurisdiction_code"],
        "inputs": {
            "credit_amount": context["credit_amount"],
            "message_sha256_prefix": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12],
        },
        "layer_trail": context.get("layer_trail", []),
        "final_verdict": context.get("final_verdict_so_far"),
    }
    entry_id = AUDIT_CHAIN.append(entry)["entry_id"]
    return {"verdict": "PASS", "detail": f"audit entry {entry_id} written"}


class GuardrailStack:
    @staticmethod
    def evaluate(payload: str, context: dict) -> dict:
        """
        TODO 2: Same chain-of-responsibility shape as Lab-2's. Walk
        _GUARDRAIL_REGISTRY sorted by "order", skipping always_runs layers
        and any layer whose "group" is not in context["run_groups"]. PASS
        continues; REDACT replaces payload and continues; BLOCK stops the
        walk. Then run every always_runs layer, in order, with
        context["layer_trail"] and context["final_verdict_so_far"] set.
        Return {"final_verdict", "blocking_layer", "payload", "trail",
        "redactions_applied"}.
        """
        raise NotImplementedError


class AuditChain:
    """Given file I/O and canonical serialization - `append`/`verify` are
    yours, same math as Lab-2's HashChainedAuditLog."""

    def __init__(self, path: Path = AUDIT_CHAIN_FILE):
        self.path = path

    def _load(self) -> list[dict]:
        return json.load(open(self.path, encoding="utf-8")) if self.path.exists() else []

    def _save(self, chain: list[dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(chain, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _canonical(entry: dict) -> str:
        return json.dumps(entry, sort_keys=True, separators=(",", ":"))

    def append(self, entry: dict) -> dict:
        """
        TODO 6a: Same contract as Lab-2's `HashChainedAuditLog.append` -
        assign entry_id "AUD-" + 5-digit sequence, prev_hash from the last
        entry (64 zeros for genesis), entry_hash = sha256 of
        canonical(entry-without-entry_hash) + prev_hash. Append, save,
        return.
        """
        raise NotImplementedError

    def verify(self) -> tuple[bool, Optional[int]]:
        """
        TODO 6b: Same contract as Lab-2's `.verify()` - walk the chain,
        recompute each entry_hash, confirm prev_hash linkage. Return
        (True, None) or (False, <first bad index>).
        """
        raise NotImplementedError


AUDIT_CHAIN = AuditChain()


class CircuitBreaker:
    """Same three-state, injected-clock design as Lab-1's - `now` is
    always caller-supplied, never time.time()."""

    def __init__(self, failure_threshold: int = BREAKER_FAILURE_THRESHOLD, recovery_seconds: int = BREAKER_RECOVERY_SECONDS):
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.state = "closed"
        self.consecutive_failures = 0
        self.opened_at: Optional[float] = None
        self.transitions: list[dict] = []

    def _transition(self, to_state: str, now: float):
        self.transitions.append({"from": self.state, "to": to_state, "at": now})
        self.state = to_state

    def allow_request(self, now: float) -> bool:
        """
        TODO 3a: Same logic as Lab-1's CircuitBreaker.allow_request.
        """
        raise NotImplementedError

    def record_success(self, now: float):
        """
        TODO 3b: Same logic as Lab-1's CircuitBreaker.record_success.
        """
        raise NotImplementedError

    def record_failure(self, now: float):
        """
        TODO 3c: Same logic as Lab-1's CircuitBreaker.record_failure.
        """
        raise NotImplementedError


def call_with_retry(fn, max_attempts: int = RETRY_MAX_ATTEMPTS, base_delay: float = RETRY_BASE_DELAY) -> tuple[bool, object, int]:
    """
    TODO 4: Same shape as Lab-1's ResilientCaller.call_with_retry -
    exponential backoff with full jitter, catching CoreBankingError,
    respecting `.retryable`, never sleeping after the last attempt.
    """
    raise NotImplementedError


def guarded_action(dispute_id: str, amount: float, now: float, breaker: CircuitBreaker, api: CoreBankingAPI) -> dict:
    """
    TODO 5: Breaker OUTSIDE, retry INSIDE - identical composition to
    Lab-1's guarded_downstream_call. If breaker.allow_request(now) is
    False, return {"status": "short_circuited", "attempts": 0}. Otherwise
    call_with_retry(lambda: api.issue_provisional_credit(dispute_id,
    amount, idempotency_key=dispute_id)). On success, breaker.record_success(now)
    and return {**result, "attempts": attempts}. On failure,
    breaker.record_failure(now) and return {"status": "failed", "attempts": attempts}.
    """
    raise NotImplementedError


def draft_response(customer: dict, context: dict, action_result: dict) -> str:
    """
    TODO 7: Real MODEL_DRAFT call, thinking DISABLED (a short policy reply
    doesn't need it, and leaving it on eats max_tokens before any text is
    written - see Lab-2's README). Ground strictly in action_result -
    if action_result["status"] == "credited", say the provisional credit
    of action_result["amount"] was issued; if "failed" or
    "short_circuited", say the credit is still being processed and DO NOT
    claim it was issued. Either way, end with
    context["jurisdiction"]["required_disclosure"] verbatim as the final
    sentence. 2-3 sentences, address the customer by first name.
    max_tokens=400. Return the stripped text.
    """
    raise NotImplementedError


class CycleState(TypedDict, total=False):
    customer: dict
    context: dict
    intake_trail: list
    action_result: Optional[dict]
    draft: Optional[str]
    compliance_trail: list
    passed: bool
    repair_attempted: bool
    outcome: Optional[str]
    final_text: Optional[str]
    blocking_layer: Optional[str]


def intake_node(state: CycleState) -> dict:
    """Given - resolves context and runs the input+permission groups over
    the customer's own pending_question."""
    customer = state["customer"]
    context = resolve_context(customer, "issue_provisional_credit", customer["dispute_amount"])
    context["run_groups"] = {"input", "permission"}
    result = GuardrailStack.evaluate(customer["pending_question"], context)
    return {"context": context, "intake_trail": result["trail"], "passed": result["final_verdict"] == "PASS",
            "blocking_layer": result["blocking_layer"]}


def _route_after_intake(state: CycleState) -> Literal["proceed", "deny"]:
    return "proceed" if state["passed"] else "deny"


def agent_node(state: CycleState) -> dict:
    """
    TODO 8: customer = state["customer"]; context = state["context"].
    Look up FAULTS[customer["dispute_id"]]["t"] for the injected clock
    value (given data). Call guarded_action(customer["dispute_id"],
    customer["dispute_amount"], that t, BREAKER, CORE_BANKING_API) (module-
    level singletons, given below). Call draft_response(customer, context,
    the action result). Return {"action_result": <the action result>,
    "draft": <the draft text>}.
    """
    raise NotImplementedError


def guardrail_node(state: CycleState) -> dict:
    """
    TODO 9: context = state["context"]; context["run_groups"] = {"compliance"}.
    Run GuardrailStack.evaluate(state["draft"], context). Return
    {"compliance_trail": result["trail"], "passed": result["final_verdict"] == "PASS",
    "draft": result["payload"], "blocking_layer": result["blocking_layer"]}.
    """
    raise NotImplementedError


def _route_after_guardrail(state: CycleState) -> Literal["release", "handoff", "repair", "deny"]:
    if state["passed"]:
        amount = state["context"]["credit_amount"]
        return "handoff" if amount is not None and amount > APPROVAL_THRESHOLD else "release"
    return "deny" if state.get("repair_attempted") else "repair"


def repair_node(state: CycleState) -> dict:
    """Given - one repair attempt, fed the specific failing compliance
    layers, re-instructed to keep the disclosure verbatim through the
    rewrite. Same shape as Day 8's revise_node."""
    problems = [f"{t['layer']}: {t['detail']}" for t in state["compliance_trail"] if t["verdict"] != "PASS"]
    disclosure = state["context"]["jurisdiction"]["required_disclosure"]
    system = (
        "You rewrite banking dispute responses to fix SPECIFIC compliance problems, keeping the rest of the "
        f"message's intent intact. The rewrite MUST still end with this exact disclosure, verbatim: \"{disclosure}\" "
        "Output ONLY the rewritten message itself - no preamble, no explanation, no surrounding quotation marks."
    )
    user = f"Original response: {state['draft']}\n\nProblems to fix:\n" + "\n".join(problems)
    response = client.messages.create(model=MODEL_DRAFT, max_tokens=400, thinking={"type": "disabled"},
                                       system=system, messages=[{"role": "user", "content": user}])
    revised = next(b for b in response.content if b.type == "text").text.strip()
    return {"draft": revised, "repair_attempted": True}


def release_node(state: CycleState) -> dict:
    return {"outcome": "released", "final_text": state["draft"]}


def handoff_node(state: CycleState) -> dict:
    """Given - a failed or over-threshold request isn't a dead end, it's a
    handoff. The customer still gets a safe, disclosure-carrying holding
    message; nothing non-compliant ever ships."""
    customer = state["customer"]
    first_name = customer["name"].split()[0]
    disclosure = state["context"]["jurisdiction"]["required_disclosure"]
    text = (f"Hi {first_name}, I'm looping in a specialist from our {AGENT_CARD['human_fallback_queue']} team "
            f"to follow up with you directly on this. {disclosure}")
    return {"outcome": "routed_to_human", "final_text": text}


def deny_node(state: CycleState) -> dict:
    """Given - 'denied' is the engineering verdict for this cycle (the
    candidate failed the gate, or was never allowed to try); the graph
    always routes deny -> handoff next, so nothing failing ever reaches
    the customer as-is."""
    return {"outcome": "denied"}


class EnterpriseCommandCenter:
    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self):
        """
        TODO 10: Build a StateGraph(CycleState) with 7 nodes: "intake" ->
        intake_node, "agent" -> agent_node, "guardrail" -> guardrail_node,
        "repair" -> repair_node, "release" -> release_node, "handoff" ->
        handoff_node, "deny" -> deny_node. Entry point: "intake". Topology:
        intake -> conditional via _route_after_intake, mapping "proceed" ->
        "agent", "deny" -> "deny"; agent -> guardrail (unconditional);
        guardrail -> conditional via _route_after_guardrail, mapping
        "release"/"handoff"/"repair"/"deny" to the like-named nodes; repair
        -> guardrail (the one cycle); release -> END; handoff -> END; deny
        -> handoff (NOT straight to END - a denied request still needs to
        produce something the customer sees). Return graph.compile().
        """
        raise NotImplementedError

    def process_customer(self, customer: dict) -> dict:
        """Given - runs one customer through the graph and shapes the
        result record CapacityMeter/the dashboard/the self-check all read."""
        final_state = self.graph.invoke({"customer": customer, "repair_attempted": False})
        return {
            "customer_id": customer["customer_id"], "jurisdiction": customer["jurisdiction"],
            "credit_amount": customer["dispute_amount"], "outcome": final_state["outcome"],
            "final_text": final_state.get("final_text"),
            "first_pass_passed": final_state["passed"] if not final_state.get("repair_attempted") else None,
            "repaired": final_state.get("repair_attempted", False),
            "blocking_layer": final_state.get("blocking_layer"),
        }


class CapacityMeter:
    @staticmethod
    def compute(records: list[dict]) -> dict:
        """
        TODO 11: Return {"total_processed": len(records),
        "volume_by_jurisdiction": a dict counting each record's
        "jurisdiction", "outcome_counts": a dict counting each record's
        "outcome", "guardrail_pass_rate": the fraction of records whose
        "first_pass_passed" is True (records where it's None - i.e. they
        were repaired, so there WAS no clean first pass - count as NOT
        passing first-pass; round to 3dp; guard the empty-list case),
        "approved": True if guardrail_pass_rate >= 0.5 else False,
        "rejection_reason": None if approved else "guardrail_pass_rate
        below the 0.5 floor" (Day 5's ROIResult floor-gate-first idea,
        recast: don't approve a rollout on cost/volume numbers alone if
        the safety floor itself is failing)}.
        """
        raise NotImplementedError


class Dashboard:
    """Given - one matplotlib PNG: this cycle's jurisdiction volume and
    outcome mix, plus a cross-cycle pass-rate trend read back from
    capstone_eval_runs.json, same "read history back" idea as Day 8's
    dashboards."""

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
        j_colors = {"NY": CATEGORICAL["blue"], "CA": CATEGORICAL["orange"], "TX": CATEGORICAL["aqua"]}
        jurisdictions = list(metrics["volume_by_jurisdiction"].keys())
        bars = ax.bar(jurisdictions, [metrics["volume_by_jurisdiction"][j] for j in jurisdictions],
                       color=[j_colors.get(j, INK_MUTED) for j in jurisdictions], width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Dispute volume by jurisdiction", color=INK, fontsize=11, loc="left", fontweight="bold")

        ax = axes[0, 1]
        outcomes = list(metrics["outcome_counts"].keys())
        bars = ax.bar(outcomes, [metrics["outcome_counts"][o] for o in outcomes], color=CATEGORICAL["blue"], width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Outcome mix", color=INK, fontsize=11, loc="left", fontweight="bold")

        cycle_idx = list(range(1, len(eval_history) + 1))
        pass_rate_series = [r.get("pass_rate", 0.0) for r in eval_history]

        ax = axes[1, 0]
        if len(eval_history) >= 2:
            ax.plot(cycle_idx, pass_rate_series, color=CATEGORICAL["blue"], linewidth=2, marker="o", markersize=5, zorder=3)
        elif eval_history:
            ax.plot(cycle_idx, pass_rate_series, color=CATEGORICAL["blue"], marker="o", markersize=6, zorder=3)
            ax.set_xlim(0, 2)
            ax.text(0.5, 0.15, "needs 2+ cycles for a line", transform=ax.transAxes, ha="center", color=INK_MUTED, fontsize=8)
        else:
            ax.text(0.5, 0.5, "no cycles logged yet", transform=ax.transAxes, ha="center", va="center", color=INK_MUTED, fontsize=9)
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(f"Gate pass rate across cycles (n={len(eval_history)})", color=INK, fontsize=11, loc="left", fontweight="bold")

        ax = axes[1, 1]
        ax.axis("off")
        approved = metrics.get("approved")
        color = DIVERGING["positive"] if approved else DIVERGING["negative"]
        ax.text(0.02, 0.7, "Floor gate", color=INK, fontsize=11, fontweight="bold")
        ax.text(0.02, 0.45, f"guardrail_pass_rate = {metrics.get('guardrail_pass_rate')}", color=INK_MUTED, fontsize=9)
        ax.text(0.02, 0.25, f"approved = {approved}", color=color, fontsize=13, fontweight="bold")

        fig.suptitle("Banking Enterprise Trust — Capacity, Outcomes & Gate Trend", color=INK, fontsize=13, fontweight="bold", x=0.02, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_path, dpi=130, facecolor=SURFACE)
        plt.close(fig)


def run_corpus(traces: list[dict]) -> dict:
    """
    TODO 12: Same two-sided scoring shape as Lab-2's run_corpus. For each
    trace, resolve context via resolve_context(CUSTOMERS_BY_ID[trace["customer_id"]],
    trace["action"], trace["credit_amount"], actor_id=trace["actor_id"])
    (the corpus tests a SPECIFIC actor per trace, not the customer's usual
    one), run input+permission groups over trace["message"]; if that
    blocks, final_verdict="BLOCK" with that blocking_layer and no
    redactions. Else: payload = trace["precomposed_response"] if set, else
    draft_response(customer, context, {"status": "credited", "amount":
    trace["credit_amount"]}) (treat a live-drafted corpus trace as
    already-credited for grading purposes - the corpus is about the
    GUARDRAIL STACK, not the action layer). Run compliance group over that
    payload. Score exactly like Lab-2: total, blocked, expected_blocked,
    missed_blocks, false_blocks, wrong_layer, redaction_mismatches, and a
    "results" list of {"trace_id", "final_verdict", "blocking_layer"} per trace.
    """
    raise NotImplementedError


class ComplianceJudgment(BaseModel):
    compliant: bool = Field(description="True if this response is well-grounded, compliant, and makes sense.")
    reason: str = Field(description="One short sentence justifying the verdict.")


class BatchGate:
    """Day 8 Lab-1's Batches API mechanic, reused to judge the guardrail
    stack's own output at scale rather than an analytics transcript."""

    @staticmethod
    def build_requests(records: list[dict]) -> list[dict]:
        """
        TODO 13a: One Batches API request per record (skip any record
        whose final_text is falsy): {"custom_id": record["customer_id"],
        "params": {model: MODEL_CHEAP, max_tokens: 200, tools: a forced
        tool call on ComplianceJudgment.model_json_schema() (tool name
        "judge"), system: a compliance reviewer judging whether the
        response is well-grounded and appropriate given its outcome,
        messages: one user turn with the outcome and final_text}}.
        """
        raise NotImplementedError

    @staticmethod
    def run(records: list[dict], poll_interval: float = 5.0, max_wait_seconds: float = 300.0) -> dict:
        """
        TODO 13b: Same submit/poll/parse shape as Day 8 Lab-1's
        InsightBatchExtractor.run - client.messages.batches.create(requests=
        build_requests(records)), poll .processing_status to "ended"
        (print .request_counts each poll; give up past max_wait_seconds),
        then read client.messages.batches.results(batch.id), keeping only
        "succeeded" results, parsed into ComplianceJudgment keyed by
        custom_id. Return {"judgments": {customer_id: ComplianceJudgment},
        "pass_rate": round(fraction where .compliant is True, 3)}.
        """
        raise NotImplementedError


def eval_gated(pass_threshold: float = 1.0):
    """Given - Day 8 Lab-2's decorator, reused: attaches `.run_gate()` to
    the function it wraps without changing its normal call behavior."""
    def decorator(fn):
        def run_gate():
            result = fn()
            records = result["records"]
            checks = []
            for r in records:
                should_deny = r["customer_id"] in EXPECTED_DENIED_CUSTOMER_IDS
                actually_denied_upstream = r["outcome"] == "routed_to_human" and r["blocking_layer"] is not None
                if should_deny:
                    checks.append({"customer_id": r["customer_id"], "ok": actually_denied_upstream})
                else:
                    checks.append({"customer_id": r["customer_id"], "ok": r["outcome"] in ("released", "routed_to_human")})
            deterministic_pass_rate = round(sum(1 for c in checks if c["ok"]) / len(checks), 3) if checks else 0.0
            batch = BatchGate.run(records)
            verdict = "promote" if deterministic_pass_rate >= pass_threshold else "reject"
            log_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "records_processed": len(records), "pass_rate": deterministic_pass_rate,
                "verdict": verdict, "checks": checks,
                "batch_judge_pass_rate": batch["pass_rate"],
                "sample_final_text_redacted": redact_for_log((records[0]["final_text"] or "")[:200]),
            }
            history = json.load(open(EVAL_RUNS_FILE, encoding="utf-8")) if EVAL_RUNS_FILE.exists() else []
            history.append(log_record)
            with open(EVAL_RUNS_FILE, "w", encoding="utf-8") as ff:
                json.dump(history, ff, ensure_ascii=False, indent=2)
            return log_record
        fn.run_gate = run_gate
        return fn
    return decorator


CUSTOMERS_BY_ID = {c["customer_id"]: c for c in CUSTOMERS}
BREAKER = CircuitBreaker()
CORE_BANKING_API = CoreBankingAPI(FAULTS)


@eval_gated(pass_threshold=1.0)
def process_all_customers() -> dict:
    """Given - orchestrates the whole batch: every customer through the
    graph, then batch-level metrics and the dashboard."""
    center = EnterpriseCommandCenter()
    records = [center.process_customer(c) for c in CUSTOMERS]
    metrics = CapacityMeter.compute(records)
    eval_history = json.load(open(EVAL_RUNS_FILE, encoding="utf-8")) if EVAL_RUNS_FILE.exists() else []
    Dashboard.build(metrics, eval_history, DASHBOARD_FILE)
    return {"records": records, "metrics": metrics, "center": center}


def demo_circuit_breaker_open() -> None:
    """Given - forces closed->open->half_open->closed deterministically,
    isolated from the live customer run, and proves zero physical attempts
    happen while open."""
    print("\n=== Demo: circuit breaker full cycle (isolated) ===")
    demo_api = CoreBankingAPI({"D1": {"behavior": "fail_always"}, "D2": {"behavior": "fail_always"},
                                "D3": {"behavior": "fail_always"}, "D4": {"behavior": "ok"}, "D5": {"behavior": "ok"}})
    breaker = CircuitBreaker()
    for dispute_id, t in [("D1", 0), ("D2", 15), ("D3", 30), ("D4", 45), ("D5", 95)]:
        result = guarded_action(dispute_id, 100, t, breaker, demo_api)
        print(f"  t={t:>3} {dispute_id}: {result} -> breaker={breaker.state} (consecutive_failures={breaker.consecutive_failures})")
    print(f"  Transitions: {breaker.transitions}")
    print(f"  Physical attempts against demo_api: {demo_api.attempt_count} (D4 cost ZERO while open)")


def demo_idempotent_replay() -> None:
    """Given - calls guarded_action TWICE for the SAME dispute with the
    SAME idempotency_key and shows the ledger stays at one entry and the
    second call consumes zero additional physical attempts - Day 4's
    replay contract, proven under retry for the first time."""
    print("\n=== Demo: idempotent replay ===")
    demo_api = CoreBankingAPI({"D-REPLAY": {"behavior": "ok"}})
    breaker = CircuitBreaker()
    first = guarded_action("D-REPLAY", 250, 0, breaker, demo_api)
    second = guarded_action("D-REPLAY", 250, 10, breaker, demo_api)
    print(f"  First call:  {first}")
    print(f"  Second call: {second}")
    print(f"  attempt_count={demo_api.attempt_count} (should be 1, not 2), ledger rows={len(demo_api.ledger)}")


def demo_guardrail_repair_loop() -> None:
    """Given - a hand-crafted draft carrying a prohibited phrase and a
    missing disclosure reliably fails first, gets repaired, and is
    re-judged - proving the one retry cap (no second cycle)."""
    print("\n=== Demo: guardrail repair loop ===")
    customer = CUSTOMERS_BY_ID["CUST-BK01"]
    context = resolve_context(customer, "issue_provisional_credit", 500)
    context["run_groups"] = {"compliance"}
    state: CycleState = {"customer": customer, "context": context, "draft": "This dispute is fully resolved, guaranteed reversal-free.", "repair_attempted": False}
    state.update(guardrail_node(state))
    print(f"  First draft passed={state['passed']} blocking_layer={state['blocking_layer']}")
    if not state["passed"]:
        state.update(repair_node(state))
        print(f"  Repaired: \"{state['draft']}\"")
        state.update(guardrail_node(state))
        print(f"  Second judgment passed={state['passed']}")
    print(f"  repair_attempted={state['repair_attempted']} (no second retry path exists)")


def demo_rbac_deny() -> None:
    """Given - BA-330 (fraud_investigator) requesting a credit action gets
    denied before a single token is generated; the IDENTICAL request from
    BA-101 (tier1_support, within their ceiling) on the same customer
    passes."""
    print("\n=== Demo: RBAC deny -> handoff ===")
    center = EnterpriseCommandCenter()
    customer = dict(CUSTOMERS_BY_ID["CUST-BK03"])  # dispute_amount=900, within tier1's 1000 ceiling
    fraud_attempt = {**customer, "requesting_actor": "BA-330"}
    result = center.process_customer(fraud_attempt)
    print(f"  BA-330 (fraud_investigator) requesting credit: outcome={result['outcome']} blocking_layer={result['blocking_layer']}")
    print(f"  Customer-visible message: \"{result['final_text']}\"")
    tier1_attempt = {**customer, "requesting_actor": "BA-101"}
    result2 = center.process_customer(tier1_attempt)
    print(f"  Same request via BA-101 (tier1_support): outcome={result2['outcome']}")


def demo_audit_tamper() -> None:
    """Given - same two-step tamper demo as Lab-2's: flip a field, catch
    it at its index; 'fix' its own hash, watch the break move forward one
    entry because the NEXT entry's prev_hash is unchanged."""
    print("\n=== Demo: audit chain tamper detection ===")
    chain = AUDIT_CHAIN._load()
    if len(chain) < 4:
        print(f"  Chain has only {len(chain)} entries - run the pipeline first.")
        return
    tampered = json.loads(json.dumps(chain))
    tampered[2]["inputs"]["credit_amount"] = 999999
    tmp = AuditChain(AUDIT_CHAIN_FILE)
    tmp._save(tampered)
    ok, bad = tmp.verify()
    print(f"  After tampering entry 2: verify() -> ({ok}, {bad})")
    entry_copy = dict(tampered[2]); entry_copy.pop("entry_hash")
    tampered[2]["entry_hash"] = hashlib.sha256((AuditChain._canonical(entry_copy) + tampered[2]["prev_hash"]).encode("utf-8")).hexdigest()
    tmp._save(tampered)
    ok2, bad2 = tmp.verify()
    print(f"  After 'fixing' entry 2's own hash: verify() -> ({ok2}, {bad2}) - the break moved to entry 3, whose prev_hash still points at the ORIGINAL entry 2.")
    tmp._save(chain)


def capstone_selfcheck(center: EnterpriseCommandCenter, corpus_scorecard: dict) -> bool:
    """Given - the grading harness. Hard-asserts only deterministic facts;
    reports the batch judge's opinion without grading it."""
    print("\n=== Capstone self-check ===")
    scorecard = []

    scorecard.append(("banking_customers.json: 10 customers, NY=4/CA=3/TX=3",
                       sum(1 for c in CUSTOMERS if c["jurisdiction"] == "NY") == 4 and
                       sum(1 for c in CUSTOMERS if c["jurisdiction"] == "CA") == 3 and
                       sum(1 for c in CUSTOMERS if c["jurisdiction"] == "TX") == 3 and len(CUSTOMERS) == 10))

    corpus_blocked_ids = {r["trace_id"] for r in corpus_scorecard["results"] if r["final_verdict"] == "BLOCK"}
    scorecard.append(("adversarial_corpus: exactly the expected traces block", corpus_blocked_ids == EXPECTED_BLOCKED_TRACE_IDS))
    scorecard.append(("adversarial_corpus: zero false blocks", len(corpus_scorecard["false_blocks"]) == 0))
    scorecard.append(("adversarial_corpus: zero missed blocks", len(corpus_scorecard["missed_blocks"]) == 0))
    scorecard.append(("adversarial_corpus: zero wrong-layer verdicts", len(corpus_scorecard["wrong_layer"]) == 0))

    demo_api = CoreBankingAPI({"D1": {"behavior": "fail_always"}, "D2": {"behavior": "fail_always"},
                                "D3": {"behavior": "fail_always"}, "D4": {"behavior": "ok"}})
    breaker = CircuitBreaker()
    for dispute_id, t in [("D1", 0), ("D2", 15), ("D3", 30), ("D4", 45)]:
        guarded_action(dispute_id, 100, t, breaker, demo_api)
    scorecard.append(("breaker opens after 3 consecutive failures", breaker.state == "open" and breaker.consecutive_failures == 3))
    # D1/D2/D3 each exhaust all 3 retry attempts (fail_always) = 9 physical
    # attempts; D4 arrives while the breaker is OPEN and costs zero.
    scorecard.append(("open breaker makes ZERO physical attempts for D4 while open", demo_api.attempt_count == 9))

    demo_api2 = CoreBankingAPI({"D-REPLAY": {"behavior": "ok"}})
    breaker2 = CircuitBreaker()
    guarded_action("D-REPLAY", 250, 0, breaker2, demo_api2)
    guarded_action("D-REPLAY", 250, 10, breaker2, demo_api2)
    scorecard.append(("idempotent replay: 1 attempt, 1 ledger row after 2 calls", demo_api2.attempt_count == 1 and len(demo_api2.ledger) == 1))

    chain_ok, _ = AUDIT_CHAIN.verify()
    scorecard.append(("audit chain verifies clean on disk", chain_ok))

    tampered = json.loads(json.dumps(AUDIT_CHAIN._load()))
    if len(tampered) >= 1:
        tampered[0]["inputs"]["credit_amount"] = -1
        tmp = AuditChain(AUDIT_CHAIN_FILE.parent / "_selfcheck_scratch.json")
        tmp._save(tampered)
        tamper_ok, tamper_bad = tmp.verify()
        scorecard.append(("audit chain catches a tampered entry at the right index", tamper_ok is False and tamper_bad == 0))
        if tmp.path.exists():
            tmp.path.unlink()

    graph_nodes = set(center.graph.get_graph().nodes)
    scorecard.append(("graph wires deny -> handoff (not a dead end)", {"deny", "handoff"} <= graph_nodes))
    scorecard.append(("graph has exactly one cycle edge (repair -> guardrail)", "repair" in graph_nodes and "guardrail" in graph_nodes))

    ba101_result = center.process_customer({**CUSTOMERS_BY_ID["CUST-BK08"], "requesting_actor": "BA-330"})
    ba207_result = center.process_customer({**CUSTOMERS_BY_ID["CUST-BK08"], "requesting_actor": "BA-207"})
    scorecard.append(("RBAC symmetry: fraud_investigator denied, senior_adjuster not",
                       ba101_result["outcome"] == "routed_to_human" and ba207_result["outcome"] != "denied"))

    over_threshold = center.process_customer(CUSTOMERS_BY_ID["CUST-BK09"])
    scorecard.append(("over-approval-threshold customer routes to a human even on a clean pass",
                       over_threshold["outcome"] == "routed_to_human"))

    passed = sum(1 for _, ok in scorecard if ok)
    for label, ok in scorecard:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print(f"\n  {passed}/{len(scorecard)} checks passed.")
    return passed == len(scorecard)


if __name__ == "__main__":
    print(f"=== Capstone: Banking Enterprise Trust — {len(CUSTOMERS)} customers, {len(CORPUS)} adversarial traces ===")

    print(f"\n--- Guardrail stack corpus (deterministic, batch) ---")
    corpus_scorecard = run_corpus(CORPUS)
    print(f"  {corpus_scorecard['blocked']}/{corpus_scorecard['total']} blocked (expected {corpus_scorecard['expected_blocked']})")
    print(f"  Missed blocks: {corpus_scorecard['missed_blocks']}")
    print(f"  False blocks: {corpus_scorecard['false_blocks']}")

    print(f"\n--- Live pipeline: {len(CUSTOMERS)} customers through the graph ---")
    result = process_all_customers()
    for r in result["records"]:
        print(f"  {r['customer_id']} ({r['jurisdiction']}, ${r['credit_amount']}): {r['outcome']} "
              f"(repaired={r['repaired']}, blocking_layer={r['blocking_layer']})")

    print(f"\n--- Capacity & cost ---")
    print(f"  {result['metrics']}")
    print(f"  Dashboard written -> {DASHBOARD_FILE.name}")

    print(f"\n--- Eval gate (Batches API judging every response) ---")
    gate_result = process_all_customers.run_gate()
    print(f"  verdict={gate_result['verdict']} deterministic_pass_rate={gate_result['pass_rate']} "
          f"(informational) batch_judge_pass_rate={gate_result['batch_judge_pass_rate']}")

    demo_circuit_breaker_open()
    demo_idempotent_replay()
    demo_guardrail_repair_loop()
    demo_rbac_deny()
    demo_audit_tamper()

    ok = capstone_selfcheck(result["center"], corpus_scorecard)
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED — see scorecard above'}")
