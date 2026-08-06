"""
Lab-1: Telecom - The Call Center Falls Over the Moment It Gets Popular (STARTER).

Eighteen contacts arrive at a simulated CCaaS shift. Two things can go wrong
that have nothing to do with what the customer said: the downstream system
this center depends on can be flaky (CoreStatusAPI), and the queues customers
route into have finite capacity. Neither failure mode is solved by a better
prompt - they're solved by a circuit breaker, a retry policy, and a capacity
governor, the same three primitives every real CCaaS integration needs
regardless of which model is drafting the reply.

You'll build:
  1. CircuitBreaker - three states (closed/open/half_open), an INJECTED clock
     (never time.time() in a decision path - the shift's own `t` values drive
     every state transition, which is what makes the breaker's behavior
     reproducible in a report instead of dependent on wall-clock luck).
  2. ResilientCaller.call_with_retry - exponential backoff + full jitter,
     retryable-vs-fatal classification, a hard attempt cap.
  3. guarded_downstream_call - composes the two: breaker OUTSIDE (decides
     whether to even try), retry INSIDE (decides how hard to try once let
     through). Get this order backwards and a single flaky call burns your
     retry budget before the breaker ever gets a vote.
  4. classify_contact - the one model judgment this lab makes, and the one
     call that must never crash the shift: on any API error it degrades to
     an "unclassified" default rather than raising.
  5. QueueRouter.select_queue + CapacityGovernor.admit - deterministic
     skill-based routing with real concurrency limits, so a full primary
     queue sheds to a secondary, and a full secondary sheds to overflow.
  6. draft_holding_message - cost-tiered: a classification that degraded
     gets a free templated reply, everyone else gets a real model draft
     sized to their segment.
  7. WarmHandoffPackager.build - the model writes the human-readable
     summary, the system attaches the facts (customer, queue, downstream
     status) - the model never has to be trusted to get the facts right.
"""

import json
import random
import sys
import time
from pathlib import Path
from typing import Literal, Optional

from anthropic import Anthropic, APIStatusError, APITimeoutError, RateLimitError
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_CHEAP = "claude-haiku-4-5-20251001"
MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "ccaas_queues.json", encoding="utf-8") as f:
    _QUEUE_DATA = json.load(f)
    QUEUES = {q["queue_id"]: q for q in _QUEUE_DATA["queues"]}
    ROUTING_CHAINS = _QUEUE_DATA["routing_chains"]
with open(DATA_DIR / "agent_roster.json", encoding="utf-8") as f:
    AGENTS = json.load(f)["agents"]
with open(DATA_DIR / "contact_events.json", encoding="utf-8") as f:
    CONTACTS = json.load(f)["contacts"]

RUN_HISTORY_FILE = DATA_DIR / "resilience_runs.json"

OVERFLOW_QUEUE_ID = "Q-OVERFLOW"
INTENT_SKILL = {"billing": "billing", "technical": "technical", "retention": "retention"}

BREAKER_FAILURE_THRESHOLD = 3
BREAKER_RECOVERY_SECONDS = 90
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.4

# Anthropic client with the SDK's own reliability knobs made explicit rather
# than silently accepted - a short client-level timeout and a SINGLE
# client-level retry, so our own ResilientCaller (not the SDK's hidden retry
# loop) is what a student actually observes and can reason about.
client = Anthropic(max_retries=1, timeout=30.0)

random.seed(9)


class DownstreamError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class CoreStatusAPI:
    """Given - the flaky downstream dependency every contact checks before a
    reply goes out (e.g. "is there a known outage on this account"). Behavior
    is fixed per contact_id by contact_events.json's `downstream_fault`
    field, not randomized - the whole point of this lab is a reliability
    report whose facts don't move between runs."""

    def __init__(self, contacts: list[dict]):
        self._fault_by_contact = {c["contact_id"]: c["downstream_fault"] for c in contacts}
        self._calls_so_far: dict[str, int] = {}
        self.attempt_count = 0

    def check(self, contact_id: str) -> dict:
        self.attempt_count += 1
        behavior = self._fault_by_contact[contact_id]
        n = self._calls_so_far.get(contact_id, 0)
        self._calls_so_far[contact_id] = n + 1
        if behavior == "ok":
            return {"status": "clear"}
        if behavior == "fail_once":
            if n == 0:
                raise DownstreamError("core-status-api: 500", retryable=True)
            return {"status": "clear"}
        if behavior == "fail_twice":
            if n < 2:
                raise DownstreamError("core-status-api: 500", retryable=True)
            return {"status": "clear"}
        if behavior == "fail_always":
            raise DownstreamError("core-status-api: 500", retryable=True)
        raise ValueError(f"unknown fault behavior: {behavior}")


class ContactClassification(BaseModel):
    urgency: Literal["low", "medium", "high"] = Field(description="How urgent this contact is.")
    needs_human: bool = Field(description="True if this genuinely needs a human, not just a policy lookup.")
    summary: str = Field(description="One short sentence summarizing what the customer wants.")


class CircuitBreaker:
    """Three states, one injected clock. `now` is always a caller-supplied
    number (this lab's contact `t` in seconds) - never time.time() - so the
    exact same sequence of calls produces the exact same transition log
    every run."""

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
        TODO 1a: True if state == "closed". If state == "open": once
        `now - self.opened_at >= self.recovery_seconds`, call
        self._transition("half_open", now) and return True (this is the ONE
        probe request half-open exists to allow) - otherwise return False
        (still short-circuiting). If state == "half_open", return True (a
        probe is already in flight; this simulation is sequential so there's
        never a second concurrent one to worry about).
        """
        raise NotImplementedError

    def record_success(self, now: float):
        """
        TODO 1b: If state == "half_open", the probe worked - call
        self._transition("closed", now). Either way (closed or half_open),
        a success resets self.consecutive_failures to 0 - a clean call
        erases the failure streak regardless of what state it happened in.
        """
        raise NotImplementedError

    def record_failure(self, now: float):
        """
        TODO 1c: Increment self.consecutive_failures. If state == "half_open",
        the probe failed - set self.opened_at = now and
        self._transition("open", now) (reopen, restarting the recovery
        clock). Elif state == "closed" and consecutive_failures has now
        reached self.failure_threshold, set self.opened_at = now and
        self._transition("open", now). No transition fires on a failure
        while already "open" (it's not accepting requests to fail).
        """
        raise NotImplementedError


class ResilientCaller:
    @staticmethod
    def call_with_retry(fn, max_attempts: int = RETRY_MAX_ATTEMPTS, base_delay: float = RETRY_BASE_DELAY) -> tuple[bool, object, int]:
        """
        TODO 2: Call fn() up to max_attempts times. On success, return
        (True, result, attempt_number). On a DownstreamError: if
        `not e.retryable` OR this was the last attempt, return
        (False, None, attempt_number) immediately - don't sleep after a
        result you're not going to retry. Otherwise sleep
        `random.uniform(0, base_delay * 2**(attempt-1))` (full jitter,
        exponential backoff by attempt number) and continue to the next
        attempt. This is the ONE place in this lab that does a real
        time.sleep - the dead air is deliberate, not a bug to optimize away.
        """
        raise NotImplementedError


def guarded_downstream_call(contact_id: str, now: float, breaker: CircuitBreaker, api: CoreStatusAPI) -> dict:
    """
    TODO 3: If breaker.allow_request(now) is False, return
    {"status": "short_circuited", "attempts": 0} - no physical call at all.
    Otherwise call ResilientCaller.call_with_retry(lambda: api.check(contact_id)).
    On success, call breaker.record_success(now) and return
    {"status": "clear", "attempts": <attempts>}. On failure, call
    breaker.record_failure(now) and return
    {"status": "failed", "attempts": <attempts>}. Breaker OUTSIDE, retry
    INSIDE - the breaker decides whether to try at all; the retry policy
    only ever runs once that gate has already said yes.
    """
    raise NotImplementedError


def classify_contact(contact: dict) -> dict:
    """
    TODO 4: Real MODEL_CHEAP call, forced tool use on
    ContactClassification.model_json_schema() (tool name "classify"). System
    prompt: a telecom triage assistant judging urgency, whether this
    genuinely needs a human (not just a policy lookup), and a one-sentence
    summary. User content: this contact's channel and message. On success
    return {"urgency":..., "needs_human":..., "summary":..., "degraded": False}
    from the parsed tool input. Wrap the call in try/except catching
    (APIStatusError, APITimeoutError, RateLimitError) - on any of those,
    return {"urgency": "medium", "needs_human": False,
    "summary": "(classification unavailable)", "degraded": True} instead of
    letting the exception propagate. A shift report that crashes because one
    classification call timed out is a worse outcome than one contact
    getting a conservative default.
    """
    raise NotImplementedError


class CapacityGovernor:
    """Deterministic. Tracks, per queue, the departure time of every contact
    currently occupying a slot; admits a new arrival only if fewer than
    `max_concurrent` slots are still occupied at that arrival's own `t`."""

    def __init__(self, queues: dict):
        self.queues = queues
        self._active: dict[str, list[float]] = {qid: [] for qid in queues}

    def admit(self, queue_id: str, now: float) -> bool:
        """
        TODO 5: Prune self._active[queue_id] down to departures strictly
        greater than `now` (anything that's already finished by `now` no
        longer occupies a slot). If the pruned list's length is less than
        this queue's "max_concurrent", admit: append
        `now + queue["handle_seconds"]` to the active list and return True.
        Otherwise return False - the queue is full at this instant.
        """
        raise NotImplementedError


class QueueRouter:
    @staticmethod
    def select_queue(channel_intent: str, now: float, governor: CapacityGovernor) -> dict:
        """
        TODO 6: Look up this intent's chain in ROUTING_CHAINS (default
        [OVERFLOW_QUEUE_ID] for an intent with no chain, e.g. "other").
        Walk the chain in order; for the first queue_id where
        governor.admit(queue_id, now) returns True, return
        {"queue_id": queue_id, "hops": <its index in the chain>, "reason": ...}.
        `reason` is "no_matching_queue" if the chain only had one entry to
        begin with (there was never a real primary to shed FROM), else
        "direct" if hops == 0, else "capacity_shed". If every queue in the
        chain is full (shouldn't happen given overflow's capacity, but don't
        let it crash), fail safe: return
        {"queue_id": OVERFLOW_QUEUE_ID, "hops": len(chain), "reason": "capacity_shed"}.
        """
        raise NotImplementedError


def draft_holding_message(contact: dict, classification: dict) -> dict:
    """
    TODO 7: If classification.get("degraded") is True, return a short
    templated reply (no model call) with "tier": "template" - if the triage
    itself is untrustworthy, don't spend a second call compounding the
    uncertainty. Otherwise: tier = "sonnet" if contact["segment"] ==
    "premium" else "haiku", model = MODEL_DRAFT for sonnet else MODEL_CHEAP.
    Real call: system prompt asks for a short (1-2 sentence) warm telecom
    support holding reply, no fabricated account details, no unverifiable
    promises; user content = the contact's message and the classification's
    urgency. max_tokens=150. Return {"text": <stripped>, "tier": tier}.
    """
    raise NotImplementedError


class WarmHandoffPackager:
    @staticmethod
    def build(contact: dict, classification: dict, routed_queue: str, agents: list[dict]) -> dict:
        """
        TODO 8: required_skill = "escalation" if routed_queue is the
        overflow queue, else INTENT_SKILL.get(contact["channel_intent"],
        "escalation"). assigned_agent = the agent_id of the first agent in
        `agents` that is available AND has required_skill in its skills
        list, or None if none qualify - HA-104 being offline and the only
        escalation-skilled agent is exactly what makes some handoffs land
        on None, a real operational state, not a bug to special-case away.
        Real MODEL_CHEAP call (max_tokens=100): one short sentence briefing
        a human agent, from the contact's message and the classification's
        summary - this is the ONLY thing the model writes; return
        {"required_skill":..., "assigned_agent":..., "summary": <the model
        sentence>, "facts": {"customer_id":..., "channel":...,
        "routed_queue": routed_queue, "urgency": classification["urgency"]}}
        - the facts dict comes straight from data, never from the model.
        """
        raise NotImplementedError


def append_shift_run(report: dict, history_path: Path = RUN_HISTORY_FILE) -> dict:
    """Given - one record per shift, appended, never overwritten."""
    history = json.load(open(history_path, encoding="utf-8")) if history_path.exists() else []
    history.append(report)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return report


def demo_circuit_breaker_cycle() -> None:
    """Given - replays the exact fault sequence that trips the breaker in
    this shift, isolated from routing/drafting, so the closed->open->
    half_open->closed cycle can be read on its own."""
    print("\n=== Demo: circuit breaker full cycle, isolated ===")
    demo_api = CoreStatusAPI(CONTACTS)
    breaker = CircuitBreaker()
    trace = [("CT-004", 45), ("CT-005", 60), ("CT-006", 75), ("CT-007", 90), ("CT-012", 170), ("CT-013", 185), ("CT-016", 230)]
    for contact_id, t in trace:
        result = guarded_downstream_call(contact_id, t, breaker, demo_api)
        print(f"  t={t:>3} {contact_id}: {result} -> breaker now {breaker.state} (consecutive_failures={breaker.consecutive_failures})")
    print(f"  Transition log: {breaker.transitions}")


def demo_degraded_classification() -> None:
    """Given - no live contact in this fixture happens to trip
    classify_contact's own except-branch, so the free template tier never
    fires in the main run. This proves it directly: a hand-built degraded
    classification still produces a safe, zero-cost reply rather than a
    crash or a silently-skipped customer."""
    print("\n=== Demo: degraded classification -> free template reply ===")
    degraded = {"urgency": "medium", "needs_human": False, "summary": "(classification unavailable)", "degraded": True}
    reply = draft_holding_message(CONTACTS[0], degraded)
    print(f"  tier={reply['tier']} (no model call made) -> \"{reply['text']}\"")


if __name__ == "__main__":
    print(f"=== Lab-1: Telecom Contact Center — {len(CONTACTS)} contacts, one simulated shift ===\n")

    api = CoreStatusAPI(CONTACTS)
    breaker = CircuitBreaker()
    governor = CapacityGovernor(QUEUES)

    results = []
    for contact in CONTACTS:
        now = contact["t"]
        classification = classify_contact(contact)
        routing = QueueRouter.select_queue(contact["channel_intent"], now, governor)
        downstream = guarded_downstream_call(contact["contact_id"], now, breaker, api)

        # Deliberately NOT gated on classification["needs_human"] - that's the
        # model's opinion and stays informational (reported below, never
        # decisive). The branch that actually escalates a human is pure
        # system policy: a downstream we can't trust, or a queue that
        # couldn't take this contact on its own skill.
        handoff_needed = downstream["status"] in ("short_circuited", "failed") or routing["queue_id"] == OVERFLOW_QUEUE_ID
        if handoff_needed:
            handoff = WarmHandoffPackager.build(contact, classification, routing["queue_id"], AGENTS)
            outcome = "handoff"
            reply_tier = None
        else:
            reply = draft_holding_message(contact, classification)
            handoff = None
            outcome = "self_serve"
            reply_tier = reply["tier"]

        results.append({
            "contact_id": contact["contact_id"], "customer_id": contact["customer_id"], "t": now,
            "channel_intent": contact["channel_intent"], "queue": routing["queue_id"], "hops": routing["hops"],
            "routing_reason": routing["reason"], "downstream": downstream, "breaker_state_after": breaker.state,
            "classification": classification, "outcome": outcome, "reply_tier": reply_tier, "handoff": handoff,
        })
        print(f"  t={now:>3} {contact['contact_id']} ({contact['customer_id']}, {contact['channel_intent']}) "
              f"-> {routing['queue_id']} (hops={routing['hops']}, {routing['reason']}) | "
              f"downstream={downstream['status']}(attempts={downstream['attempts']}) | breaker={breaker.state} | {outcome}"
              + (f" tier={reply_tier}" if reply_tier else f" -> {handoff['assigned_agent'] or 'UNASSIGNED'} ({handoff['required_skill']})"))

    print(f"\n--- Circuit breaker ---")
    print(f"  Final state: {breaker.state}, consecutive_failures={breaker.consecutive_failures}")
    print(f"  Transitions: {breaker.transitions}")
    print(f"  Total physical attempts against CoreStatusAPI: {api.attempt_count}")

    print(f"\n--- Routing & capacity ---")
    by_queue = {}
    for r in results:
        by_queue.setdefault(r["queue"], []).append(r["contact_id"])
    for qid, cids in by_queue.items():
        print(f"  {qid}: {len(cids)} contacts -> {cids}")
    shed_count = sum(1 for r in results if r["hops"] > 0)
    print(f"  Contacts that shed at least one hop: {shed_count}")

    print(f"\n--- Outcomes ---")
    handoffs = [r for r in results if r["outcome"] == "handoff"]
    self_serve = [r for r in results if r["outcome"] == "self_serve"]
    unassigned = [r for r in handoffs if r["handoff"]["assigned_agent"] is None]
    print(f"  Handoff: {len(handoffs)} ({[r['contact_id'] for r in handoffs]})")
    print(f"  Unassigned (no available agent with required skill): {len(unassigned)} ({[r['contact_id'] for r in unassigned]})")
    print(f"  Self-serve: {len(self_serve)}, by tier: "
          f"{ {t: sum(1 for r in self_serve if r['reply_tier'] == t) for t in ('template', 'haiku', 'sonnet')} }")

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_contacts": len(CONTACTS),
        "breaker_transitions": breaker.transitions,
        "breaker_final_state": breaker.state,
        "breaker_final_consecutive_failures": breaker.consecutive_failures,
        "total_downstream_attempts": api.attempt_count,
        "volume_by_queue": {qid: len(cids) for qid, cids in by_queue.items()},
        "shed_count": shed_count,
        "handoff_count": len(handoffs),
        "unassigned_handoff_count": len(unassigned),
        "self_serve_by_tier": {t: sum(1 for r in self_serve if r["reply_tier"] == t) for t in ("template", "haiku", "sonnet")},
    }
    record = append_shift_run(report)
    print(f"\n--- Shift recorded -> {RUN_HISTORY_FILE.name} ---")

    demo_circuit_breaker_cycle()
    demo_degraded_classification()
