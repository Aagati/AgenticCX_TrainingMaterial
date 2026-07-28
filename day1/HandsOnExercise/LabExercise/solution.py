"""
Lab Exercise — Banking: Grounded Dispute Resolution, End to End (REFERENCE SOLUTION)

Covers TODO 1-8 from starter.py. Part B's reference lives in
solution_langchain.py, which imports the domain core from this file — the
enforcement layer is framework-independent, and proving that is half the
lesson of Part B.

Run the scripted conversations:      python solution.py
Run the keyless safety checks:       python solution.py --selftest
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5"

HERE = Path(__file__).parent
POLICY_KB = json.loads((HERE / "dispute_policy.json").read_text(encoding="utf-8"))
TRANSACTIONS = json.loads((HERE / "transactions.json").read_text(encoding="utf-8"))

AGENT_AUTHORITY_LIMIT = 5000
VALID_REASON_CODES = {"FRAUD", "SERVICE_NOT_RENDERED", "GOODS_NOT_RECEIVED"}
PLACEHOLDERS = {"tbd", "n/a", "na", "unknown", "none", "-", "todo", "null"}

STOPWORDS = {"the", "is", "a", "an", "of", "to", "for", "my", "does", "do",
             "what", "how", "if", "and", "on", "in", "it", "am", "i", "can",
             "was", "are", "this", "that", "with", "but", "not", "you"}

_client = None


def get_client() -> Anthropic:
    """Lazy — so solution_langchain.py (and --selftest) can import the domain
    core without an API key present."""
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# --------------------------------------------------------------- TODO 1
def retrieve_policy(query: str, top_k: int = 3) -> list:
    """Token-overlap retrieval over the dispute policy.

    Clauses scoring 0 are dropped rather than padded in. An agent that gets
    handed an irrelevant clause will cite it — the empty list is what lets it
    say "the policy doesn't cover this" instead."""
    q_tokens = set(_tokenize(query))
    scored = []
    for clause in POLICY_KB:
        clause_tokens = set(_tokenize(clause["title"] + " " + clause["text"]))
        scored.append((len(q_tokens & clause_tokens), clause))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [clause for score, clause in scored[:top_k] if score > 0]


# --------------------------------------------------------------- TODO 2
class DisputeFiling(BaseModel):
    """Arguments for the irreversible action. Every field here is something
    the model asserts; the validators below are the cheapest place to catch
    the assertions that are structurally impossible."""

    transaction_id: str = Field(description="Id of the transaction to dispute, e.g. TXN-9001.")
    reason_code: str = Field(description="One of: FRAUD, SERVICE_NOT_RENDERED, GOODS_NOT_RECEIVED.")
    amount: int = Field(description="Disputed amount in INR. Must match the transaction exactly.")
    customer_confirmed: bool = Field(
        description="True ONLY if the customer gave explicit confirmation in a message that came "
                    "after you described the consequences. Vague replies are not confirmation."
    )
    cited_clauses: List[str] = Field(
        description="Policy clause ids (e.g. DSP-004) you relied on when explaining this to the customer."
    )

    @field_validator("reason_code")
    @classmethod
    def _known_reason(cls, v: str) -> str:
        if v not in VALID_REASON_CODES:
            raise ValueError(f"reason_code must be one of {sorted(VALID_REASON_CODES)}, got {v!r}")
        return v

    @field_validator("amount")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"amount must be positive, got {v}")
        return v

    @field_validator("customer_confirmed")
    @classmethod
    def _must_be_confirmed(cls, v: bool) -> bool:
        # Deliberately fails rather than defaulting to a safe no-op. A filing
        # request that admits the customer never agreed is a bug in the caller,
        # and silently dropping it would hide that bug.
        if v is not True:
            raise ValueError(
                "customer_confirmed must be True — file_dispute cannot be called before the "
                "customer has explicitly confirmed."
            )
        return v


# --------------------------------------------------------------- TODO 3
class EscalationPayload(BaseModel):
    """Everything the specialist needs to act without calling the customer back."""

    summary: str = Field(description="What happened, in 1-2 concrete sentences.")
    transaction_id: Optional[str] = Field(default=None, description="Transaction id if one is involved.")
    amount: Optional[int] = Field(default=None, description="Disputed amount in INR if applicable.")
    customer_sentiment: str = Field(description="How the customer is feeling and how urgent this is to them.")
    requested_action: str = Field(description="What the customer actually asked you to do.")
    cited_clauses: List[str] = Field(description="Policy clause ids that made this an escalation.")
    conversation_transcript: str = Field(description="Full exchange so far, so nothing is re-asked.")

    @field_validator("summary", "customer_sentiment", "requested_action", "conversation_transcript")
    @classmethod
    def _no_placeholders(cls, v: str, info) -> str:
        stripped = (v or "").strip()
        if not stripped:
            raise ValueError(f"{info.field_name} must not be empty")
        if stripped.lower() in PLACEHOLDERS:
            raise ValueError(
                f"{info.field_name} is a placeholder ({stripped!r}) — fill it with specifics "
                "from this conversation"
            )
        return stripped


# ------------------------------------------------------------ tool schemas
LOOKUP_TRANSACTION_TOOL = {
    "name": "lookup_transaction",
    "description": (
        "Look up a card transaction by its id. Returns merchant, amount, "
        "card_last4, status (posted|pending), statement_date, and whether it "
        "is already under dispute. Call this before discussing any specific "
        "transaction — never assume an amount or a status."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"transaction_id": {"type": "string"}},
        "required": ["transaction_id"],
    },
}

SEARCH_POLICY_TOOL = {
    "name": "search_dispute_policy",
    "description": (
        "Search the card dispute policy for clauses relevant to a question. "
        "Returns clause ids and text. Call this before stating ANY rule, "
        "timeline, limit or consequence to the customer."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

# TODO 4. The two descriptions are written to be mutually exclusive on the one
# axis that decides between them — the authority limit — because that is the
# routing decision the model gets wrong when left to infer it.
FILE_DISPUTE_TOOL = {
    "name": "file_dispute",
    "description": (
        f"File a dispute on a POSTED transaction of {AGENT_AUTHORITY_LIMIT} INR or less. "
        "IRREVERSIBLE when reason_code is FRAUD: the card is permanently blocked and a "
        "replacement is issued; the blocked card number can never be reinstated. Call this "
        "ONLY after the customer has explicitly confirmed, in a message that came after you "
        f"described that consequence. For amounts above {AGENT_AUTHORITY_LIMIT} INR use "
        "escalate_to_human instead — you are not authorised to file those, and must not ask "
        "the customer to confirm one."
    ),
    "input_schema": DisputeFiling.model_json_schema(),
}

ESCALATE_TOOL = {
    "name": "escalate_to_human",
    "description": (
        "Hand this conversation to a disputes specialist. Use this when the disputed amount "
        f"exceeds your {AGENT_AUTHORITY_LIMIT} INR authority, or when the customer explicitly "
        "asks for a human. Fill every field with specifics from this conversation — the "
        "specialist works the case without the customer on the line, so a placeholder makes "
        "the handoff useless."
    ),
    "input_schema": EscalationPayload.model_json_schema(),
}

_case_counter = {"n": 40021}
_ticket_counter = {"n": 55107}


# ---------------------------------------------------------- tool executors
def lookup_transaction(transaction_id: str) -> dict:
    txn = TRANSACTIONS.get(transaction_id)
    if txn is None:
        return {"error": f"no transaction found with id {transaction_id}"}
    return {"transaction_id": transaction_id, **txn}


# --------------------------------------------------------------- TODO 1b
def search_dispute_policy(query: str) -> dict:
    clauses = retrieve_policy(query)
    if not clauses:
        # Explicit, not an empty list. "No clauses matched" and "no restrictions
        # apply" are opposite meanings and the model will conflate them if the
        # result is just [].
        return {"clauses": [],
                "note": "No policy clauses matched this query. Do not infer a rule from this — "
                        "say you could not find the relevant policy."}
    return {"clauses": [{"id": c["id"], "title": c["title"], "text": c["text"]} for c in clauses]}


# --------------------------------------------------------------- TODO 5
def file_dispute(**kwargs) -> dict:
    """The irreversible action, and the only place in this lab where safety is
    actually enforced rather than merely requested.

    The system prompt states every rule below, and the model follows them most
    of the time. This function is what holds when it doesn't — write it as if
    a jailbroken model were the caller, because eventually one is."""

    # a) shape
    try:
        filing = DisputeFiling(**kwargs)
    except ValidationError as e:
        return {"error": f"dispute filing rejected: {e}"}

    # b) business rules, re-checked against real data rather than the model's word
    txn = TRANSACTIONS.get(filing.transaction_id)
    if txn is None:
        return {"error": f"no transaction found with id {filing.transaction_id}"}

    if txn["status"] != "posted":
        return {"error": f"transaction {filing.transaction_id} is {txn['status']}, not posted — "
                         "it cannot be disputed yet (DSP-003)"}

    if txn.get("under_dispute"):
        return {"error": f"transaction {filing.transaction_id} is already under dispute as "
                         f"{txn.get('existing_case_ref', 'an existing case')} — a duplicate "
                         "filing would delay both cases (DSP-006)"}

    if filing.amount != txn["amount"]:
        return {"error": f"amount mismatch: filing says {filing.amount}, transaction is "
                         f"{txn['amount']}"}

    if filing.amount > AGENT_AUTHORITY_LIMIT:
        # The one that matters. Reached only when prompt AND tool description
        # have both failed, which is exactly when you want a hard stop.
        return {"error": f"amount {filing.amount} exceeds the agent authority limit of "
                         f"{AGENT_AUTHORITY_LIMIT} INR — this must go to a specialist via "
                         "escalate_to_human (DSP-005). Not filed."}

    # c) execute
    card_blocked = filing.reason_code == "FRAUD"
    case_ref = f"CASE-{_case_counter['n']}"
    _case_counter["n"] += 1

    # Mark it disputed so a repeat call is caught by the DSP-006 branch above.
    txn["under_dispute"] = True
    txn["existing_case_ref"] = case_ref

    print(f"[SYSTEM] Dispute filed on {filing.transaction_id} for {filing.amount} INR "
          f"({filing.reason_code}). Case {case_ref}.")
    if card_blocked:
        print(f"[SYSTEM] Card ending {txn['card_last4']} PERMANENTLY BLOCKED. "
              "Replacement issued. This cannot be undone.")

    return {"case_ref": case_ref, "status": "filed", "provisional_credit_days": 10,
            "card_blocked": card_blocked}


# --------------------------------------------------------------- TODO 6
def escalate_to_human(**kwargs) -> dict:
    try:
        payload = EscalationPayload(**kwargs)
    except ValidationError as e:
        return {"error": f"escalation payload rejected: {e}"}

    ticket_id = f"TCK-{_ticket_counter['n']}"
    _ticket_counter["n"] += 1

    print(f"[SYSTEM] Escalated to disputes specialist. Ticket {ticket_id}.")
    print(f"         summary: {payload.summary}")
    print(f"         wants:   {payload.requested_action}")
    print(f"         mood:    {payload.customer_sentiment}")
    print(f"         cites:   {', '.join(payload.cited_clauses) or '(none)'}")

    return {"ticket_id": ticket_id, "status": "queued_for_specialist", "eta_business_days": 1}


TOOLS = [LOOKUP_TRANSACTION_TOOL, SEARCH_POLICY_TOOL, FILE_DISPUTE_TOOL, ESCALATE_TOOL]
TOOL_FUNCS = {
    "lookup_transaction": lookup_transaction,
    "search_dispute_policy": search_dispute_policy,
    "file_dispute": file_dispute,
    "escalate_to_human": escalate_to_human,
}


# --------------------------------------------------------------- TODO 7
SYSTEM_PROMPT = f"""You are a card disputes agent for a retail bank. You can file
disputes up to {AGENT_AUTHORITY_LIMIT} INR. Above that you cannot file at all.

Work in this order, every time:

1. GROUND BEFORE YOU SPEAK. Call search_dispute_policy before stating any rule,
   timeline, limit or consequence, and cite the clause ids you used (e.g.
   DSP-004) in your reply. Call lookup_transaction before discussing any
   transaction's amount or status. Never state a number you have not looked up.

2. CHECK AUTHORITY BEFORE ASKING ANYTHING. Once you know the amount, decide
   which tool applies. If it is above {AGENT_AUTHORITY_LIMIT} INR, escalate
   immediately with escalate_to_human. Do NOT ask the customer to confirm a
   dispute you are not allowed to file — asking, getting a yes, and then
   withdrawing is worse for them than escalating straight away. Do not promise
   or imply that the refund is approved.

3. CONFIRM BEFORE THE IRREVERSIBLE STEP. Within your limit, and only then:
   explain what filing does in plain language — for FRAUD, that the card is
   permanently blocked and cannot be reinstated — and ask for explicit
   confirmation. Treat "maybe", "I think so", "I guess", "if you say so" as NOT
   confirmation: acknowledge the hesitation and ask once more, clearly. Call
   file_dispute only after a clear yes in a message that came after your
   explanation.

4. HAND OFF WHOLE. When you escalate, fill every field of escalate_to_human
   with specifics from this conversation, including the full transcript. Never
   write "TBD" or "unknown".

If a transaction cannot be disputed — it is pending, or already under dispute —
say so directly, cite the clause, give the customer the concrete next step
(when to come back, or the existing case reference), and do not call
file_dispute at all.

Be concise and warm. The customer is worried about their money."""


# --------------------------------------------------------------- TODO 8
def run_conversation(messages: list, max_iterations: int = 6) -> list:
    """Multi-tool agentic loop. Runs deeper than H3's — a single turn is often
    search -> lookup -> search -> file."""
    client = get_client()

    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            text = "".join(b.text for b in response.content if b.type == "text")
            messages.append({"role": "assistant", "content": text})
            return messages

        messages.append({"role": "assistant", "content": response.content})

        # All results for one assistant turn go back in ONE user message.
        # Splitting them across messages trains the model out of parallel calls.
        results = []
        for block in tool_uses:
            func = TOOL_FUNCS.get(block.name)
            output = ({"error": f"unknown tool {block.name}"} if func is None
                      else func(**block.input))
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output),
            })
        messages.append({"role": "user", "content": results})

    # Loud, not silent — a loop that gives up quietly looks like one that finished.
    messages.append({
        "role": "assistant",
        "content": f"[loop halted after {max_iterations} iterations without a final reply]",
    })
    return messages


# ------------------------------------------------------- keyless self-checks
def selftest() -> int:
    """Exercises the enforcement layer directly, no model and no API key.

    These are the assertions that actually matter: every one of them is a case
    where the model has already gone wrong and the code has to hold."""
    failures = []

    def check(label, condition):
        print(f"{'PASS' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(label)

    fresh = json.loads((HERE / "transactions.json").read_text(encoding="utf-8"))
    TRANSACTIONS.clear()
    TRANSACTIONS.update(fresh)

    print("--- retrieval ---")
    for want, query in [
        ("DSP-005", "agent authority limit for filing a dispute above amount"),
        ("DSP-003", "can I dispute a pending transaction"),
        ("DSP-006", "transaction already under dispute duplicate"),
        ("DSP-004", "does filing a fraud dispute block my card permanently replacement"),
    ]:
        ids = [c["id"] for c in retrieve_policy(query)]
        check(f"{query[:44]:44s} -> {want}", want in ids)
    check("no match returns a note, not a bare empty list",
          "note" in search_dispute_policy("zzz qqq xxx unrelated"))

    print("\n--- file_dispute refuses what the prompt already forbade ---")
    ok = file_dispute(transaction_id="TXN-9001", reason_code="FRAUD", amount=1250,
                      customer_confirmed=True, cited_clauses=["DSP-004"])
    check("within-limit confirmed filing succeeds", ok.get("status") == "filed")
    check("FRAUD filing reports the card block", ok.get("card_blocked") is True)

    dup = file_dispute(transaction_id="TXN-9001", reason_code="FRAUD", amount=1250,
                       customer_confirmed=True, cited_clauses=["DSP-004"])
    check("second filing on same txn refused (DSP-006)", "error" in dup)

    over = file_dispute(transaction_id="TXN-9002", reason_code="FRAUD", amount=18400,
                        customer_confirmed=True, cited_clauses=["DSP-005"])
    check("above-limit filing refused even when 'confirmed'", "error" in over)

    unconfirmed = file_dispute(transaction_id="TXN-9002", reason_code="FRAUD", amount=18400,
                               customer_confirmed=False, cited_clauses=[])
    check("unconfirmed filing refused", "error" in unconfirmed)

    pending = file_dispute(transaction_id="TXN-9004", reason_code="FRAUD", amount=2100,
                           customer_confirmed=True, cited_clauses=["DSP-003"])
    check("pending txn refused (DSP-003)", "error" in pending)

    already = file_dispute(transaction_id="TXN-9003", reason_code="FRAUD", amount=640,
                           customer_confirmed=True, cited_clauses=["DSP-006"])
    check("already-disputed txn refused (DSP-006)", "error" in already)

    mismatch = file_dispute(transaction_id="TXN-9002", reason_code="FRAUD", amount=100,
                            customer_confirmed=True, cited_clauses=[])
    check("amount mismatch refused (can't under-report to dodge the limit)", "error" in mismatch)

    bad_code = file_dispute(transaction_id="TXN-9002", reason_code="MADE_UP", amount=18400,
                            customer_confirmed=True, cited_clauses=[])
    check("unknown reason_code refused", "error" in bad_code)

    print("\n--- escalate_to_human rejects hollow handoffs ---")
    good = escalate_to_human(
        summary="Customer reports an 18400 INR fraudulent charge at Global Travel Booking.",
        transaction_id="TXN-9002", amount=18400,
        customer_sentiment="Angry and anxious; wants immediate resolution.",
        requested_action="Block the card and refund 18400 INR.",
        cited_clauses=["DSP-005"],
        conversation_transcript="Customer: TXN-9002 is fraudulent... Agent: that is above my limit...",
    )
    check("complete payload creates a ticket", good.get("status") == "queued_for_specialist")

    hollow = escalate_to_human(
        summary="TBD", transaction_id="TXN-9002", amount=18400,
        customer_sentiment="unknown", requested_action="N/A",
        cited_clauses=[], conversation_transcript="   ",
    )
    check("placeholder payload rejected, no ticket issued",
          "error" in hollow and "ticket_id" not in hollow)

    TRANSACTIONS.clear()
    TRANSACTIONS.update(json.loads((HERE / "transactions.json").read_text(encoding="utf-8")))

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} FAILED: {failures}'}")
    return 1 if failures else 0


# --------------------------------------------------------- scripted run
def _scripted() -> None:
    print("=== 1. Within authority, FRAUD -> ground, confirm, then file ===")
    convo = [{"role": "user", "content":
              "There's a charge on my card I didn't make — TXN-9001. I want it disputed."}]
    convo = run_conversation(convo)
    print("AGENT:", convo[-1]["content"])

    convo.append({"role": "user", "content": "Hmm, I'm not sure. Maybe?"})
    convo = run_conversation(convo)
    print("\nAGENT:", convo[-1]["content"])

    convo.append({"role": "user", "content": "Yes, please block it and file the dispute."})
    convo = run_conversation(convo)
    print("\nAGENT:", convo[-1]["content"])

    print("\n=== 2. Above authority -> escalate, and never ask to confirm ===")
    convo2 = [{"role": "user", "content":
               "TXN-9002 is a fraudulent charge, 18400 rupees. Block the card and refund me now."}]
    convo2 = run_conversation(convo2)
    print("AGENT:", convo2[-1]["content"])

    print("\n=== 3. Already under dispute -> neither file nor escalate ===")
    convo3 = [{"role": "user", "content":
               "I want to dispute TXN-9003 again, nothing has happened."}]
    convo3 = run_conversation(convo3)
    print("AGENT:", convo3[-1]["content"])

    print("\n=== 4. Pending transaction -> refuse, with a date, not a shrug ===")
    convo4 = [{"role": "user", "content": "Dispute TXN-9004 please, it's wrong."}]
    convo4 = run_conversation(convo4)
    print("AGENT:", convo4[-1]["content"])


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    _scripted()
