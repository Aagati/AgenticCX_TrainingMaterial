"""
PM · H1 — Insurance Supervisor + 2 Specialist Agents (STARTER)
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
    """
    TODO 1: Implement the Claims Specialist's own tool-use loop:
      - system prompt: empathetic, status/next-step focused, has
        get_claim_status available
      - call the model with tools=[GET_CLAIM_STATUS_TOOL]
      - if it calls the tool, execute get_claim_status(), feed the result
        back, and get a final text reply
      - if it doesn't call a tool (e.g. it needs to ask which claim id),
        just return its text reply
    Return the specialist's final text reply (a string).
    """
    raise NotImplementedError


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
    """
    TODO 2: Simple keyword overlap retrieval over POLICY_CLAUSES (same
    technique as Day 1's H1 lab). Return the top 2 matches as a list of
    {id, title, text} dicts.
    """
    raise NotImplementedError


def run_policy_specialist(customer_message: str) -> str:
    """
    TODO 3: Implement the Policy Specialist's own tool-use loop:
      - system prompt: precise, citation-oriented, must use search_policy
        and answer ONLY from returned clauses, citing ids; say "I don't
        have this information" if nothing relevant is found
      - call the model with tools=[SEARCH_POLICY_TOOL], execute the tool
        when called, feed results back, get final text reply
    Return the specialist's final text reply (a string).
    """
    raise NotImplementedError


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


def run_supervisor(customer_message: str) -> str:
    """
    TODO 4: Implement the Supervisor's loop:
      - system prompt: decide whether this needs a specialist handoff
        (claims or policy) or can be handled directly (e.g. greetings);
        use the handoff tool when appropriate
      - if the model calls handoff, execute_handoff() with the actual
        customer_message as the task (or the model's task description —
        your call), feed the specialist's reply back as the tool result,
        and get a final supervisor reply that relays the answer to the
        customer in a consistent voice
      - if no handoff is called, just return the supervisor's direct reply
    Return the supervisor's final text reply.
    """
    raise NotImplementedError


if __name__ == "__main__":
    test_messages = [
        "Hi there!",
        "What's the status of claim CLM-3391?",
        "Does my auto policy cover a rental car while my car's in the shop?",
    ]
    for m in test_messages:
        print(f"\nCUSTOMER: {m}")
        print(f"AGENT: {run_supervisor(m)}")


# ============================================================
# Part 2 — Agent-Assist Mode (required)
# ============================================================
from typing import Optional
from pydantic import BaseModel, Field


class AgentAssistPayload(BaseModel):
    """
    TODO 5: Define four fields:
      - recommended_response: str
      - proposed_specialist: Optional[str] = None
      - proposed_task: Optional[str] = None
      - requires_human_approval: bool = True
    Give each a Field(description=...).
    """
    pass


def run_supervisor_agent_assist(customer_message: str) -> AgentAssistPayload:
    """
    TODO 6: Same routing logic as run_supervisor (TODO 4), but instead of
    returning the final text directly:
      - if no handoff happened, return AgentAssistPayload(recommended_response=<text>)
      - if a handoff happened, return AgentAssistPayload with
        recommended_response=<final draft text>, proposed_specialist=<which
        one>, proposed_task=<the task string that was used>
    Nothing should be printed to "the customer" — this function only ever
    returns a payload for a human to review.
    """
    raise NotImplementedError


if __name__ == "__main__":
    print("\n\n=== Part 2: Agent-Assist Mode ===")
    for m in test_messages:
        print(f"\nCUSTOMER: {m}")
        payload = run_supervisor_agent_assist(m)
        print(payload.model_dump_json(indent=2))
