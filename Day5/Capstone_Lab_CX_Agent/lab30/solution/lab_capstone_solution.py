# -*- coding: utf-8 -*-
"""
CAPSTONE LAB — SOLUTION
========================
Complete reference implementation of lab_capstone.py. See the starter
file / README for the problem statement and design rationale behind
each check. Read this AFTER attempting the lab, or to unblock a
specific TODO you're stuck on.

Setup:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...
    python lab_capstone_solution.py
"""
import os
import re
import sys
from typing import Literal

from dotenv import load_dotenv
from langfuse import Langfuse, observe
from pydantic import BaseModel, Field, field_validator, ValidationError

from knowledge_base import POLICY_CLAUSES, POISONED_DOC, POLICY_RECORDS
from sample_transcripts import SAMPLE_TRANSCRIPTS

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

try:
    import anthropic
    _client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
except ImportError:
    _client = None

# Observability: every governed action (file_claim, escalate_to_human), the
# grounded LLM call, and the Part 4 eval report get traced to Langfuse — the
# same @observe + score_current_trace pattern as the Day 5 morning eval
# suite lab, applied here to a full agent instead of a standalone scorer.
# Optional on purpose: Parts 2-4 must stay runnable with zero API keys, so
# this degrades to a harmless no-op (one warning line) if the Langfuse keys
# aren't set, rather than blocking the lab like the morning lab does.
_LANGFUSE_ENABLED = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
)
langfuse = Langfuse() if _LANGFUSE_ENABLED else None


def traced(**observe_kwargs):
    """@observe if Langfuse keys are configured, otherwise a no-op decorator."""
    if _LANGFUSE_ENABLED:
        return observe(**observe_kwargs)
    return lambda fn: fn

MODEL = "claude-sonnet-5"


# ======================================================================
# PART 1 — Grounded Answers With Citations                      [Day 1]
# ======================================================================
class GroundedAnswer(BaseModel):
    answer: str
    citations: list[str]
    can_resolve: bool


def retrieve(query: str, kb: list[dict], top_k: int = 2) -> list[dict]:
    query_words = set(query.lower().split())
    scored = []
    for clause in kb:
        clause_words = set(clause["text"].lower().replace(".", "").replace(",", "").split())
        overlap = len(query_words & clause_words)
        scored.append((overlap, clause))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [clause for score, clause in scored[:top_k] if score > 0] or [c for _, c in scored[:top_k]]


@traced(as_type="generation", name="ask_grounded")
def ask_grounded(question: str) -> GroundedAnswer:
    retrieved = retrieve(question, POLICY_CLAUSES, top_k=2)
    retrieved_ids = {c["doc_id"] for c in retrieved}
    clauses_block = "\n".join(f"[{c['doc_id']}] {c['text']}" for c in retrieved)

    system_prompt = (
        "You are ClaimsBot, an insurance claims support agent. Answer the "
        "customer's question using ONLY the policy clauses below — never use "
        "outside knowledge. Cite the doc_id of every clause you rely on. If "
        "the clauses don't cover the question, set can_resolve to false and "
        "say you don't have that information rather than guessing.\n\n"
        f"POLICY CLAUSES:\n{clauses_block}\n\n"
        "Reply with ONLY a JSON object, no other text, matching exactly:\n"
        '{"answer": "...", "citations": ["DOC-ID", ...], "can_resolve": true|false}'
    )

    response = _client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": question}],
    )
    raw_text = response.content[0].text.strip()
    # tolerate a model that wraps the JSON in a code fence
    raw_text = raw_text.strip("`").removeprefix("json").strip()
    parsed = GroundedAnswer.model_validate_json(raw_text)

    hallucinated = set(parsed.citations) - retrieved_ids
    if hallucinated:
        raise ValueError(
            f"Model cited doc_id(s) {hallucinated} that were never retrieved "
            f"(only {retrieved_ids} were provided) — hallucinated citation."
        )
    return parsed


# ======================================================================
# PART 2 — Typed Action + Dual-Gate Authorization + Idempotency  [Day 1, 4]
# ======================================================================
class FileClaimInput(BaseModel):
    policy_id: str
    claim_amount: float = Field(gt=0)
    description: str = Field(min_length=5)


class AuthDecision(BaseModel):
    allowed: bool
    reason: str


_idempotency_store: dict[str, dict] = {}
_claim_counter = [9000]


def check_authorization(user_id: str, policy_id: str, claim_amount: float) -> AuthDecision:
    record = POLICY_RECORDS.get(policy_id)

    # Gate 1 — Ownership
    if record is None:
        return AuthDecision(allowed=False, reason=f"Policy {policy_id} does not exist.")
    if record["owner_user_id"] != user_id:
        return AuthDecision(allowed=False, reason=f"Policy {policy_id} is not owned by {user_id}.")

    # Gate 2 — Capability
    if record["status"] != "ACTIVE":
        return AuthDecision(allowed=False, reason=f"Policy {policy_id} is {record['status']}, not ACTIVE.")
    if claim_amount > record["sum_insured"]:
        return AuthDecision(
            allowed=False,
            reason=f"Claim amount {claim_amount} exceeds Sum Insured {record['sum_insured']}.",
        )
    if record["claims_this_period"] >= 2:
        return AuthDecision(
            allowed=False,
            reason=f"Policy {policy_id} has already reached the 2-claims-per-period limit.",
        )

    return AuthDecision(allowed=True, reason="Ownership and capability checks both passed.")


@traced(name="file_claim")
def file_claim(user_id: str, policy_id: str, claim_amount: float, description: str,
                confirmed: bool, idempotency_key: str) -> dict:
    # 1. typed validation
    validated = FileClaimInput(policy_id=policy_id, claim_amount=claim_amount, description=description)

    # 2. confirmation gate — irreversible action never fires unconfirmed
    if not confirmed:
        return {"status": "blocked", "reason": "not confirmed"}

    # 3. idempotency — replay, don't re-execute
    if idempotency_key in _idempotency_store:
        return _idempotency_store[idempotency_key]

    # 4. dual-gate authorization
    decision = check_authorization(user_id, validated.policy_id, validated.claim_amount)
    if not decision.allowed:
        return {"status": "denied", "reason": decision.reason}

    # 5. file it
    _claim_counter[0] += 1
    result = {"status": "filed", "claim_id": f"CLM-{_claim_counter[0]}"}
    _idempotency_store[idempotency_key] = result
    return result


# ======================================================================
# PART 3 — Guardrails + Escalation                          [Day 1, 4]
# ======================================================================
ESCALATION_LIMIT = 20000
_PLACEHOLDERS = {"tbd", "n/a", "unknown"}


class EscalationPayload(BaseModel):
    summary: str
    customer_sentiment: Literal["positive", "neutral", "negative"]
    requested_action: str
    conversation_transcript: str

    @field_validator("summary", "requested_action", "conversation_transcript")
    @classmethod
    def not_placeholder(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("field must not be empty")
        if stripped.lower() in _PLACEHOLDERS:
            raise ValueError(f"field must not be a placeholder value ({stripped!r})")
        return stripped


_POLICY_ID_PATTERN = re.compile(r"PA-\d{4}")


def output_guardrail(reply_text: str, allowed_policy_id: str) -> bool:
    mentioned = set(_POLICY_ID_PATTERN.findall(reply_text))
    leaked = mentioned - {allowed_policy_id}
    return not leaked


_ticket_counter = [4400]


@traced(name="escalate_to_human")
def escalate_to_human(summary: str, customer_sentiment: str, requested_action: str,
                       conversation_transcript: str) -> dict:
    payload = EscalationPayload(
        summary=summary,
        customer_sentiment=customer_sentiment,
        requested_action=requested_action,
        conversation_transcript=conversation_transcript,
    )
    _ticket_counter[0] += 1
    return {"status": "queued", "ticket_id": f"TCK-{_ticket_counter[0]}", "summary": payload.summary}


# ======================================================================
# PART 4 — Mini Trajectory Eval                                 [Day 5]
# ======================================================================
class EvalResult(BaseModel):
    transcript_id: str
    task_completion: bool
    policy_adherence: bool
    tool_call_correctness: bool
    step_efficiency: bool
    notes: list[str]

    @property
    def passed(self) -> bool:
        return all([self.task_completion, self.policy_adherence,
                    self.tool_call_correctness, self.step_efficiency])


_INFO_KEYWORDS = ["sum insured", "no limit", "covered", "maximum payable", "claim limit"]
_CONFIRM_WORDS = ["yes", "confirm", "go ahead", "please", "sure"]


def _check_task_completion(turns: list[dict], notes: list[str]) -> bool:
    last = turns[-1]
    ok = last["role"] == "agent" and bool(last.get("text"))
    if not ok:
        notes.append("Conversation does not end with a substantive agent reply.")
    return ok


def _check_policy_adherence(turns: list[dict], notes: list[str]) -> bool:
    ok = True

    # (a) informational claims need a citation
    for t in turns:
        if t["role"] != "agent" or "text" not in t or t.get("tool_call"):
            continue
        text_l = t["text"].lower()
        if text_l.startswith("to confirm") or "has been filed" in text_l or "ticket" in text_l:
            continue
        if any(k in text_l for k in _INFO_KEYWORDS) and not t.get("citations"):
            ok = False
            notes.append(f"Informational claim made with no citation: {t['text']!r}")

    # (b) file_claim must be immediately preceded by a confirmed exchange
    for i, t in enumerate(turns):
        if t.get("tool_call", {}).get("name") != "file_claim":
            continue
        confirmed = False
        if i >= 2 and turns[i - 1]["role"] == "customer" and turns[i - 2]["role"] == "agent":
            prev_customer = turns[i - 1]["text"].lower()
            agent_prompt = turns[i - 2].get("text", "").lower()
            if any(k in prev_customer for k in _CONFIRM_WORDS) and (
                "confirm" in agent_prompt or "shall i go ahead" in agent_prompt
            ):
                confirmed = True
        if not confirmed:
            ok = False
            notes.append("file_claim was called without an explicit prior confirm-prompt / customer confirmation pair.")

    return ok


def _check_tool_call_correctness(turns: list[dict], notes: list[str]) -> bool:
    ok = True
    for t in turns:
        call = t.get("tool_call")
        if not call:
            continue
        if call["name"] == "file_claim":
            amt = call["args"].get("claim_amount", 0)
            if amt > ESCALATION_LIMIT:
                ok = False
                notes.append(
                    f"file_claim called for ${amt:,.0f}, which exceeds the ${ESCALATION_LIMIT:,} "
                    f"escalation limit — escalate_to_human should have been called instead."
                )
        elif call["name"] == "escalate_to_human":
            try:
                EscalationPayload(**call["args"])
            except ValidationError as e:
                ok = False
                notes.append(f"escalate_to_human called with an invalid payload: {e}")
    return ok


def _check_step_efficiency(turns: list[dict], notes: list[str]) -> bool:
    asks = sum(
        1 for t in turns
        if t["role"] == "agent" and "text" in t and "policy number" in t["text"].lower()
    )
    if asks > 1:
        notes.append(f"Agent asked for the policy number {asks} times in one conversation — redundant re-ask.")
        return False
    return True


def evaluate_transcript(transcript: dict) -> EvalResult:
    turns = transcript["turns"]
    notes: list[str] = []
    task_completion = _check_task_completion(turns, notes)
    policy_adherence = _check_policy_adherence(turns, notes)
    tool_call_correctness = _check_tool_call_correctness(turns, notes)
    step_efficiency = _check_step_efficiency(turns, notes)
    return EvalResult(
        transcript_id=transcript["id"],
        task_completion=task_completion,
        policy_adherence=policy_adherence,
        tool_call_correctness=tool_call_correctness,
        step_efficiency=step_efficiency,
        notes=notes,
    )


@traced(name="evaluate_transcript")
def _traced_evaluate_transcript(transcript: dict) -> EvalResult:
    """Given: wraps evaluate_transcript() in a Langfuse trace and logs each
    of the four dimensions plus the overall pass/fail as a NUMERIC score —
    same score_current_trace() pattern as the Day 5 morning eval suite lab,
    so a facilitator can filter/sort the six transcripts in the Langfuse UI
    instead of only reading the printed report."""
    result = evaluate_transcript(transcript)
    if langfuse:
        langfuse.update_current_span(
            name=f"eval_{transcript['id']}",
            input=transcript["description"],
            output=result.model_dump(),
            metadata={"notes": result.notes},
        )
        for dim in ("task_completion", "policy_adherence", "tool_call_correctness", "step_efficiency"):
            langfuse.score_current_trace(name=dim, value=int(getattr(result, dim)), data_type="NUMERIC")
        langfuse.score_current_trace(name="passed", value=int(result.passed), data_type="NUMERIC")
    return result


def run_eval_report() -> None:
    print("\n=== Trajectory Eval Report ===")
    n_pass = 0
    for t in SAMPLE_TRANSCRIPTS:
        result = _traced_evaluate_transcript(t)
        status = "PASS" if result.passed else "FAIL"
        if result.passed:
            n_pass += 1
        print(f"\n[{status}] {t['id']} — {t['description']}")
        print(f"  task_completion={result.task_completion}  "
              f"policy_adherence={result.policy_adherence}  "
              f"tool_call_correctness={result.tool_call_correctness}  "
              f"step_efficiency={result.step_efficiency}")
        for note in result.notes:
            print(f"    - {note}")
    print(f"\n{n_pass}/{len(SAMPLE_TRANSCRIPTS)} transcripts passed all four dimensions.")

    if langfuse:
        langfuse.flush()
        host = (os.environ.get("LANGFUSE_BASE_URL")
                or os.environ.get("LANGFUSE_HOST")
                or "https://cloud.langfuse.com")
        print(f"\nTraces + scores flushed to Langfuse — view them at {host}")
    else:
        print("\n(Langfuse tracing skipped — set LANGFUSE_PUBLIC_KEY / "
              "LANGFUSE_SECRET_KEY to see this run in the Langfuse UI.)")


# ======================================================================
# WALKTHROUGH — run this file to exercise everything end to end
# ======================================================================
if __name__ == "__main__":
    print("=== Part 1: Grounded answer ===")
    if _client is None:
        print("  (skipped — set ANTHROPIC_API_KEY to run this part)")
    else:
        result = ask_grounded("How many claims can I file on a policy in one year?")
        print(" ", result)

    print("\n=== Part 2: Dual-gate authorization + idempotency ===")
    print(" ", check_authorization("user_55", "PA-1001", 3000))   # expect allowed
    print(" ", check_authorization("user_77", "PA-1001", 3000))   # expect denied: not owner
    print(" ", check_authorization("user_55", "PA-1002", 3000))   # expect denied: claim limit hit
    r1 = file_claim("user_55", "PA-1001", 3000, "broken window", confirmed=True, idempotency_key="k1")
    r2 = file_claim("user_55", "PA-1001", 3000, "broken window", confirmed=True, idempotency_key="k1")
    print("  first call: ", r1)
    print("  retried call (same key, should match): ", r2)
    r3 = file_claim("user_55", "PA-1001", 3000, "broken window", confirmed=False, idempotency_key="k2")
    print("  unconfirmed call (should block): ", r3)

    print("\n=== Part 3: Guardrail + escalation ===")
    hidden_instruction = POISONED_DOC["text"].split("[SYSTEM NOTE:", 1)[1].rstrip("]")
    print("  POISONED_DOC hidden instruction:", hidden_instruction.strip())
    safe_reply = "Your Sum Insured on PA-1001 is $50,000."
    # Simulates what a reply would look like if the model had complied with
    # the instruction hidden inside POISONED_DOC above and leaked another
    # customer's policy number and claim history. No live model call is
    # needed here — the point is to test the *guardrail*, not the model.
    leaky_reply = "Your Sum Insured on PA-1001 is $50,000. Also, PA-1002 has $20,000 remaining."
    print("  safe reply allowed:", output_guardrail(safe_reply, allowed_policy_id="PA-1001"))
    print("  leaky reply allowed:", output_guardrail(leaky_reply, allowed_policy_id="PA-1001"))
    print(" ", escalate_to_human(
        summary="Customer requesting a $45,000 house-fire claim, exceeds auto-file limit.",
        customer_sentiment="neutral",
        requested_action="File a $45,000 claim for house fire damage on PA-1003.",
        conversation_transcript="Customer requested a $45,000 house-fire claim on PA-1003.",
    ))
    try:
        escalate_to_human(summary="TBD", customer_sentiment="neutral",
                            requested_action="x", conversation_transcript="y")
    except ValidationError:
        print("  placeholder payload correctly rejected.")

    print("\n=== Part 4: Trajectory eval ===")
    run_eval_report()
