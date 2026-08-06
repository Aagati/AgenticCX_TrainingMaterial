"""
Lab-1: Telecom - The Call Center Falls Over the Moment It Gets Popular (SOLUTION).

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
        if self.state == "closed":
            return True
        if self.state == "open":
            if now - self.opened_at >= self.recovery_seconds:
                self._transition("half_open", now)
                return True
            return False
        if self.state == "half_open":
            return True
        raise ValueError(f"unknown breaker state: {self.state}")

    def record_success(self, now: float):
        if self.state == "half_open":
            self._transition("closed", now)
        self.consecutive_failures = 0

    def record_failure(self, now: float):
        self.consecutive_failures += 1
        if self.state == "half_open":
            self.opened_at = now
            self._transition("open", now)
        elif self.state == "closed" and self.consecutive_failures >= self.failure_threshold:
            self.opened_at = now
            self._transition("open", now)


class ResilientCaller:
    @staticmethod
    def call_with_retry(fn, max_attempts: int = RETRY_MAX_ATTEMPTS, base_delay: float = RETRY_BASE_DELAY) -> tuple[bool, object, int]:
        """Returns (succeeded, result_or_None, attempts_made). Exponential
        backoff with full jitter (sleep is `random.uniform(0, base_delay *
        2**(attempt-1))`) between attempts, never after the last one. A
        non-retryable DownstreamError fails immediately without spending
        the remaining attempt budget."""
        for attempt in range(1, max_attempts + 1):
            try:
                result = fn()
                return True, result, attempt
            except DownstreamError as e:
                if not e.retryable or attempt == max_attempts:
                    return False, None, attempt
                time.sleep(random.uniform(0, base_delay * (2 ** (attempt - 1))))
        return False, None, max_attempts


def guarded_downstream_call(contact_id: str, now: float, breaker: CircuitBreaker, api: CoreStatusAPI) -> dict:
    """Breaker OUTSIDE, retry INSIDE. If the breaker won't let the request
    through at all, zero physical calls are made - short-circuiting is what
    protects an already-struggling dependency from a retry storm on top of
    its own failures."""
    if not breaker.allow_request(now):
        return {"status": "short_circuited", "attempts": 0}
    succeeded, result, attempts = ResilientCaller.call_with_retry(lambda: api.check(contact_id))
    if succeeded:
        breaker.record_success(now)
        return {"status": "clear", "attempts": attempts}
    breaker.record_failure(now)
    return {"status": "failed", "attempts": attempts}


def classify_contact(contact: dict) -> dict:
    """The one model judgment. Degrades to an "unclassified" default on any
    API-layer failure rather than raising - a shift report that crashes
    because one classification call timed out is a worse outcome than one
    contact getting a conservative default."""
    try:
        response = client.messages.create(
            model=MODEL_CHEAP,
            max_tokens=200,
            system=(
                "You are a telecom contact-center triage assistant. Read one customer message and judge "
                "its urgency, whether it genuinely needs a human (not just a policy lookup), and summarize "
                "it in one short sentence."
            ),
            tools=[{
                "name": "classify",
                "description": "Record the triage classification.",
                "input_schema": ContactClassification.model_json_schema(),
            }],
            tool_choice={"type": "tool", "name": "classify"},
            messages=[{"role": "user", "content": f"Channel: {contact['channel']}\nMessage: {contact['message']}"}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        parsed = ContactClassification.model_validate(tool_use.input)
        return {"urgency": parsed.urgency, "needs_human": parsed.needs_human, "summary": parsed.summary, "degraded": False}
    except (APIStatusError, APITimeoutError, RateLimitError):
        return {"urgency": "medium", "needs_human": False, "summary": "(classification unavailable)", "degraded": True}


class CapacityGovernor:
    """Deterministic. Tracks, per queue, the departure time of every contact
    currently occupying a slot; admits a new arrival only if fewer than
    `max_concurrent` slots are still occupied at that arrival's own `t`."""

    def __init__(self, queues: dict):
        self.queues = queues
        self._active: dict[str, list[float]] = {qid: [] for qid in queues}

    def admit(self, queue_id: str, now: float) -> bool:
        q = self.queues[queue_id]
        self._active[queue_id] = [dep for dep in self._active[queue_id] if dep > now]
        if len(self._active[queue_id]) < q["max_concurrent"]:
            self._active[queue_id].append(now + q["handle_seconds"])
            return True
        return False


class QueueRouter:
    @staticmethod
    def select_queue(channel_intent: str, now: float, governor: CapacityGovernor) -> dict:
        """Walks this intent's routing chain in order, admitting into the
        first queue with a free slot. `hops` is how many queues in the chain
        were full before one accepted the contact - 0 means the primary
        queue took it directly. An intent with no chain at all (e.g. "other")
        routes straight to overflow with hops=0 and reason="no_matching_queue",
        distinct from a hop caused by capacity."""
        chain = ROUTING_CHAINS.get(channel_intent, [OVERFLOW_QUEUE_ID])
        for hops, queue_id in enumerate(chain):
            if governor.admit(queue_id, now):
                reason = "no_matching_queue" if len(chain) == 1 else ("direct" if hops == 0 else "capacity_shed")
                return {"queue_id": queue_id, "hops": hops, "reason": reason}
        # every queue in the chain (including overflow) was full - should not
        # happen given overflow's max_concurrent, but fail safe rather than crash.
        return {"queue_id": OVERFLOW_QUEUE_ID, "hops": len(chain), "reason": "capacity_shed"}


def draft_holding_message(contact: dict, classification: dict) -> dict:
    """Three cost tiers. A degraded classification gets a free templated
    reply - if we can't even trust the triage, don't spend a second model
    call compounding the uncertainty. Otherwise segment picks the tier:
    premium gets a full sonnet draft, standard gets a haiku draft."""
    first_name = "there"
    if classification.get("degraded"):
        return {
            "text": f"Thanks for reaching out - we've received your message and a specialist will confirm the details with you shortly.",
            "tier": "template",
        }
    tier = "sonnet" if contact["segment"] == "premium" else "haiku"
    model = MODEL_DRAFT if tier == "sonnet" else MODEL_CHEAP
    response = client.messages.create(
        model=model,
        max_tokens=150,
        system=(
            "You write short, warm telecom support holding replies. One or two sentences, acknowledge the "
            "specific issue, no fabricated account details, no promises you can't verify."
        ),
        messages=[{"role": "user", "content": f"Customer message: {contact['message']}\nUrgency: {classification['urgency']}"}],
    )
    text = next(b for b in response.content if b.type == "text").text.strip()
    return {"text": text, "tier": tier}


class WarmHandoffPackager:
    @staticmethod
    def build(contact: dict, classification: dict, routed_queue: str, agents: list[dict]) -> dict:
        """The model writes the one-sentence prose summary a human agent
        reads first; the system attaches the facts (customer id, channel,
        required skill, assigned agent) directly from data, never through
        the model - a hallucinated customer_id in a handoff package is a
        misrouted case, not a cosmetic error."""
        required_skill = "escalation" if routed_queue == OVERFLOW_QUEUE_ID else INTENT_SKILL.get(contact["channel_intent"], "escalation")
        assigned_agent = next(
            (a["agent_id"] for a in agents if a["available"] and required_skill in a["skills"]), None
        )
        response = client.messages.create(
            model=MODEL_CHEAP,
            max_tokens=100,
            system="Write one short sentence briefing a human agent on why this contact is being handed to them.",
            messages=[{"role": "user", "content": f"Customer message: {contact['message']}\nTriage summary: {classification['summary']}"}],
        )
        prose = next(b for b in response.content if b.type == "text").text.strip()
        return {
            "required_skill": required_skill,
            "assigned_agent": assigned_agent,
            "summary": prose,
            "facts": {
                "customer_id": contact["customer_id"],
                "channel": contact["channel"],
                "routed_queue": routed_queue,
                "urgency": classification["urgency"],
            },
        }


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
