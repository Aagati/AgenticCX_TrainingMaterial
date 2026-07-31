# -*- coding: utf-8 -*-
"""
CAPSTONE LAB — Building a Governed, Evaluated CX Agent (2 hours)
==================================================================
Scenario: you're building "ClaimsBot," a claims-support agent for a
general-insurance company. Across four parts you'll implement the same
core patterns this whole program has been teaching:

  Part 1 (25 min) — Grounded answers with citations           [Day 1]
  Part 2 (35 min) — Typed action + dual-gate auth + idempotency [Day 1 & 4]
  Part 3 (30 min) — Guardrails against injection + escalation   [Day 1 & 4]
  Part 4 (20 min) — A mini trajectory eval over sample calls    [Day 5]
  Wrap-up (10 min)

Look for `# TODO` markers — that's what you implement. Everything else
(schemas, data, demo harnesses) is provided so you can spend your time
on the judgment calls, not the plumbing.

Setup:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...      # only needed for Part 1
    python lab_capstone.py            # runs a walkthrough of all 4 parts

Parts 2, 3 and 4's core logic can be implemented and tested WITHOUT an
API key — every check in those parts is plain Python logic. Only Part 1's
`ask_grounded()` calls the model.
"""
import os
import sys
from typing import Optional, Literal

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

MODEL = "claude-sonnet-5"

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


# ======================================================================
# PART 1 — Grounded Answers With Citations                      [Day 1]
# ======================================================================
class GroundedAnswer(BaseModel):
    answer: str
    citations: list[str]
    can_resolve: bool


def retrieve(query: str, kb: list[dict], top_k: int = 2) -> list[dict]:
    """TODO: return the top_k clauses from `kb` that best match `query`.

    Use simple keyword overlap (like Day 1's lab): lowercase and split
    both the query and each clause's text into words, count how many
    query words appear in the clause text, and return the top_k clauses
    with the highest overlap count. This is deliberately simple — the
    point isn't a great retriever, it's proving the pattern.
    """
    raise NotImplementedError("TODO: implement retrieve()")


@traced(as_type="generation", name="ask_grounded")
def ask_grounded(question: str) -> GroundedAnswer:
    """TODO: answer `question` using ONLY the retrieved clauses.

    Steps:
      1. Call retrieve(question, POLICY_CLAUSES, top_k=2) to get the
         relevant clauses.
      2. Call the model with a system prompt that (a) includes the
         retrieved clauses labeled by doc_id, (b) instructs it to answer
         using ONLY those clauses, (c) instructs it to cite every
         doc_id it relied on, and (d) instructs it to reply with
         can_resolve=False and no invented answer if the clauses don't
         cover the question. Ask for JSON matching GroundedAnswer's
         fields (answer, citations, can_resolve).
      3. Parse the model's JSON reply into a GroundedAnswer.
      4. VALIDATE: every doc_id in the returned `citations` must
         actually be one of the doc_ids you retrieved in step 1. If the
         model cited something it wasn't given, that's a hallucinated
         citation a schema check alone can't catch — raise a ValueError
         (or fix it up) rather than silently trusting it.
      5. Return the validated GroundedAnswer.
    """
    raise NotImplementedError("TODO: implement ask_grounded()")


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
    """TODO: implement the dual-gate authorization check.

    Look up `policy_id` in POLICY_RECORDS (knowledge_base.py). Run BOTH
    gates, in order, and return an AuthDecision explaining the first
    failure you hit (or allowed=True if both gates pass):

      Gate 1 — Ownership: the policy must exist, and its owner_user_id
               must match `user_id`. (A user asking about someone
               else's policy fails here, regardless of anything else.)

      Gate 2 — Capability: the policy's status must be "ACTIVE" (not
               LAPSED/CANCELLED), claim_amount must not exceed the
               policy's sum_insured, and claims_this_period must be
               less than 2 (mirrors POL-103's two-claims-per-year rule).

    Checking ownership alone is NOT enough — that's the "Ownership
    Only" fallacy from Day 4. Both gates must pass.
    """
    raise NotImplementedError("TODO: implement check_authorization()")


@traced(name="file_claim")
def file_claim(user_id: str, policy_id: str, claim_amount: float, description: str,
                confirmed: bool, idempotency_key: str) -> dict:
    """TODO: implement the governed file_claim action.

    Steps, in order:
      1. Validate the inputs with FileClaimInput (let a ValidationError
         propagate if invalid — don't swallow it).
      2. If `confirmed` is not True, return
         {"status": "blocked", "reason": "not confirmed"} WITHOUT
         doing anything else. An irreversible action must never fire
         without an explicit confirmation, same as Day 1's card-block
         pattern.
      3. Check `idempotency_key` against `_idempotency_store`. If this
         key has been used before, return the SAME stored result again
         — do not file a second claim.
      4. Call check_authorization(). If not allowed, return
         {"status": "denied", "reason": <AuthDecision.reason>} and do
         NOT file anything.
      5. Otherwise "file" the claim: increment _claim_counter, build a
         result dict like
         {"status": "filed", "claim_id": f"CLM-{_claim_counter[0]}"},
         store it in _idempotency_store under idempotency_key, and
         return it.
    """
    raise NotImplementedError("TODO: implement file_claim()")


# ======================================================================
# PART 3 — Guardrails + Escalation                          [Day 1, 4]
# ======================================================================
ESCALATION_LIMIT = 20000


class EscalationPayload(BaseModel):
    summary: str
    customer_sentiment: Literal["positive", "neutral", "negative"]
    requested_action: str
    conversation_transcript: str

    @field_validator("summary", "requested_action", "conversation_transcript")
    @classmethod
    def not_placeholder(cls, v: str) -> str:
        """TODO: reject empty strings and placeholder values.

        Raise ValueError if `v` (after stripping whitespace) is empty,
        or if it matches (case-insensitively) one of: "TBD", "N/A",
        "UNKNOWN". This mirrors Day 1 H3's EscalationPayload validator
        — a schema that accepts the *type* string but not a
        meaningless placeholder string.
        """
        raise NotImplementedError("TODO: implement not_placeholder validator")


def output_guardrail(reply_text: str, allowed_policy_id: str) -> bool:
    """TODO: return True if `reply_text` is SAFE to send, False to block it.

    This defends against INDIRECT prompt injection (Day 4): a poisoned
    document in the knowledge base (see POISONED_DOC) can try to trick
    the model into leaking data about policies the customer didn't ask
    about. An input guardrail can't catch this — it only ever sees the
    customer's own typed message, never the retrieved document.

    Implement this check on the OUTPUT instead: scan `reply_text` for
    any policy-id-shaped token (pattern "PA-" followed by 4 digits,
    e.g. "PA-1001"). If any such token appears that is NOT equal to
    `allowed_policy_id`, the reply is leaking information about a
    policy the customer didn't ask about — return False. Otherwise
    return True. (Hint: the `re` module's findall is enough here.)
    """
    raise NotImplementedError("TODO: implement output_guardrail()")


@traced(name="escalate_to_human")
def escalate_to_human(summary: str, customer_sentiment: str, requested_action: str,
                       conversation_transcript: str) -> dict:
    """TODO: validate and "file" an escalation.

    Build an EscalationPayload from the arguments (let ValidationError
    propagate on bad input — e.g. a placeholder value). On success,
    return {"status": "queued", "ticket_id": "TCK-<something>"} — you
    can hardcode or generate any ticket id format you like.
    """
    raise NotImplementedError("TODO: implement escalate_to_human()")


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


def evaluate_transcript(transcript: dict) -> EvalResult:
    """TODO: score one transcript on the same four dimensions Day 5 taught:

      task_completion      — does the conversation end with a
                              substantive agent reply (not a dead end)?

      policy_adherence      — (a) any agent turn that states a specific
                              policy fact (mentions "sum insured", "no
                              limit", "covered", "maximum payable" or
                              "claim limit") must carry a non-empty
                              `citations` list, UNLESS it's a
                              confirmation prompt (starts with "to
                              confirm") or a closing statement
                              (mentions "has been filed" or "ticket").
                              (b) every `file_claim` tool_call must be
                              immediately preceded by a customer turn
                              containing a confirming word ("yes",
                              "confirm", "go ahead", "please", "sure"),
                              which itself must be immediately preceded
                              by an agent turn that actually asked for
                              confirmation (contains "confirm" or
                              "shall i go ahead").

      tool_call_correctness — (a) a `file_claim` tool_call with
                              claim_amount > ESCALATION_LIMIT is the
                              WRONG tool choice (should have been
                              escalate_to_human) — fail this dimension.
                              (b) an `escalate_to_human` tool_call's
                              args must pass EscalationPayload
                              validation — if they don't, fail this
                              dimension.

      step_efficiency        — fail if the agent asks "policy number"
                              (case-insensitive substring) in more than
                              one turn in the same conversation — a
                              repeated ask for information already
                              given.

    For every failure, append a short human-readable reason to `notes`
    so the report below can explain *why* a transcript failed, not just
    that it did (mirrors Day 5's "pass rate + failure mode" reporting).
    """
    raise NotImplementedError("TODO: implement evaluate_transcript()")


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
    """Provided — runs evaluate_transcript() over every sample transcript
    and prints a pass/fail report. Run this once your Part 4 TODO is done."""
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

    print("\n=== Part 4: Trajectory eval ===")
    run_eval_report()
