"""
PM · H1 — Insurance Supervisor + 2 Specialist Agents (REFERENCE SOLUTION)
"""

import json
import re
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("claims_data.json") as f:
    CLAIMS = json.load(f)
with open("policy_clauses.json") as f:
    POLICY_CLAUSES = json.load(f)

STOPWORDS = {"the", "is", "a", "an", "of", "to", "for", "my", "does", "do",
             "what", "how", "if", "and", "on", "in", "it", "am", "i", "while"}


def _tokenize(text: str):
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# ---------- Claims Specialist ----------

GET_CLAIM_STATUS_TOOL = {
    "name": "get_claim_status",
    "description": "Look up the status, filed date, and next step for a claim by id.",
    "input_schema": {
        "type": "object",
        "properties": {"claim_id": {"type": "string"}},
        "required": ["claim_id"],
    },
}


def get_claim_status(claim_id: str) -> dict:
    for c in CLAIMS:
        if c["claim_id"] == claim_id:
            return c
    return {"error": "claim not found"}


def run_claims_specialist(customer_message: str) -> str:
    system = """You are a Claims Specialist for an insurance company. You are
empathetic and focused on claim status and next steps. Use get_claim_status
to look up any claim id mentioned. If no claim id is given, ask for one."""

    messages = [{"role": "user", "content": customer_message}]
    response = client.messages.create(
        model=MODEL, max_tokens=400, system=system,
        tools=[GET_CLAIM_STATUS_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return next(b.text for b in response.content if b.type == "text")

    result = get_claim_status(**tool_use.input)
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        tools=[GET_CLAIM_STATUS_TOOL], messages=messages,
    )
    return next(b.text for b in followup.content if b.type == "text")


# ---------- Policy Specialist ----------

SEARCH_POLICY_TOOL = {
    "name": "search_policy",
    "description": "Keyword-search the policy clause knowledge base and return matching clauses.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}


def search_policy(query: str) -> list:
    q_tokens = set(_tokenize(query))
    scored = []
    for c in POLICY_CLAUSES:
        c_tokens = set(_tokenize(c["title"] + " " + c["text"]))
        score = len(q_tokens & c_tokens)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in scored[:2] if score > 0]


def run_policy_specialist(customer_message: str) -> str:
    system = """You are a Policy Specialist for an insurance company. You are
precise and citation-oriented. Use search_policy to find relevant clauses,
then answer ONLY from what search_policy returns, citing clause ids like
[POL-010] for every factual claim. If nothing relevant is found, say you
don't have that information rather than guessing."""

    messages = [{"role": "user", "content": customer_message}]
    response = client.messages.create(
        model=MODEL, max_tokens=400, system=system,
        tools=[SEARCH_POLICY_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return next(b.text for b in response.content if b.type == "text")

    result = search_policy(**tool_use.input)
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        tools=[SEARCH_POLICY_TOOL], messages=messages,
    )
    return next(b.text for b in followup.content if b.type == "text")


# ---------- Supervisor ----------

HANDOFF_TOOL = {
    "name": "handoff",
    "description": "Hand off the customer's message to a specialist sub-agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "specialist": {"type": "string", "enum": ["claims", "policy"]},
            "task": {"type": "string", "description": "What the specialist should address"},
        },
        "required": ["specialist", "task"],
    },
}


def execute_handoff(specialist: str, task: str) -> str:
    if specialist == "claims":
        return run_claims_specialist(task)
    elif specialist == "policy":
        return run_policy_specialist(task)
    return "Unknown specialist."


SUPERVISOR_SYSTEM = """You are the front-line supervisor for an insurance CX
system. For claim status / filing questions, hand off to the "claims"
specialist. For coverage / policy wording questions, hand off to the
"policy" specialist. For greetings, thanks, or anything that doesn't need a
specialist, just reply directly yourself — don't hand off unnecessarily.
When you do hand off, pass the customer's actual question as the task."""


def run_supervisor(customer_message: str) -> str:
    messages = [{"role": "user", "content": customer_message}]
    response = client.messages.create(
        model=MODEL, max_tokens=400, system=SUPERVISOR_SYSTEM,
        tools=[HANDOFF_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return next(b.text for b in response.content if b.type == "text")

    specialist_reply = execute_handoff(**tool_use.input)
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": specialist_reply}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=350, system=SUPERVISOR_SYSTEM,
        tools=[HANDOFF_TOOL], messages=messages,
    )
    return next(b.text for b in followup.content if b.type == "text")


if __name__ == "__main__":
    test_messages = [
        "Hi there!",
        "What's the status of claim CLM-3391?",
        "Does my auto policy cover a rental car while my car's in the shop?",
    ]
    for m in test_messages:
        print(f"\nCUSTOMER: {m}")
        print(f"AGENT: {run_supervisor(m)}")

# Expected: msg 1 -> supervisor answers directly, no handoff.
# msg 2 -> handoff to claims -> get_claim_status(CLM-3391) -> under review, adjuster inspection.
# msg 3 -> handoff to policy -> search_policy -> cites POL-012 (rental reimbursement).


# ============================================================
# Part 2 — Agent-Assist Mode
# ============================================================
# Same routing and specialist research as Part 1. The only thing that
# changes is the LAST step: instead of relaying straight to the customer,
# the supervisor's draft is packaged for a human to approve first.

from typing import Optional
from pydantic import BaseModel, Field


class AgentAssistPayload(BaseModel):
    recommended_response: str = Field(description="Draft reply a human agent could send as-is or edit")
    proposed_specialist: Optional[str] = Field(default=None, description="Which specialist was consulted, if any")
    proposed_task: Optional[str] = Field(default=None, description="The task passed to that specialist, if any")
    requires_human_approval: bool = Field(default=True, description="Always True — nothing reaches the customer automatically")


def run_supervisor_agent_assist(customer_message: str) -> AgentAssistPayload:
    messages = [{"role": "user", "content": customer_message}]
    response = client.messages.create(
        model=MODEL, max_tokens=400, system=SUPERVISOR_SYSTEM,
        tools=[HANDOFF_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use is None:
        # No specialist needed — still routed through the same draft-only contract.
        draft = next(b.text for b in response.content if b.type == "text")
        return AgentAssistPayload(recommended_response=draft)

    specialist = tool_use.input["specialist"]
    task = tool_use.input["task"]
    specialist_reply = execute_handoff(specialist, task)

    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": specialist_reply}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=350, system=SUPERVISOR_SYSTEM,
        tools=[HANDOFF_TOOL], messages=messages,
    )
    draft = next(b.text for b in followup.content if b.type == "text")

    return AgentAssistPayload(
        recommended_response=draft,
        proposed_specialist=specialist,
        proposed_task=task,
    )


if __name__ == "__main__":
    print("\n\n=== Part 2: Agent-Assist Mode ===")
    for m in test_messages:
        print(f"\nCUSTOMER: {m}")
        payload = run_supervisor_agent_assist(m)
        print(payload.model_dump_json(indent=2))

# Expected: same routing decisions as Part 1, but every result is now a
# payload with requires_human_approval=True — nothing was sent to the
# "customer" automatically. proposed_specialist/proposed_task are populated
# only when a handoff actually happened (msg 1 leaves them None).
