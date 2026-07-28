"""
PM · H1 — Insurance Supervisor + 2 Specialist Agents (REFERENCE SOLUTION)

THE PATTERN: a supervisor agent that delegates to tool-using sub-agents.

Two upgrades over AM · H2's routing lab:

  * The supervisor is an agent, not a classifier. It decides whether a
    specialist is needed at all — greetings get answered directly.
  * The specialists own tools instead of being handed all the data. Each
    fetches only what the question needs.

The key idea is that delegation is just tool use. execute_handoff() runs a
whole sub-agent, but the supervisor only ever sees a tool_result — identical
in shape to what get_claim_status returns. That's why the same run_agent_loop()
drives all three agents, and why adding a third specialist means adding one
enum value and one handler, not a new control-flow branch.

Reading order:
    run_agent_loop        -> the protocol, implemented once
    claims / policy       -> two specialists, one tool each
    supervisor            -> the same loop, where the "tool" is a sub-agent
    Part 2                -> the same system with the last step changed
"""

import json
import os
import re
import sys
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# Windows consoles default to cp1252 and crash when the model emits an arrow,
# em-dash or curly quote. Force UTF-8 so a print() cannot kill the lab.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = Anthropic()
MODEL = "claude-sonnet-5"

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DATA_DIR, "claims_data.json")) as f:
    CLAIMS = json.load(f)
with open(os.path.join(DATA_DIR, "policy_clauses.json")) as f:
    POLICY_CLAUSES = json.load(f)

STOPWORDS = {"the", "is", "a", "an", "of", "to", "for", "my", "does", "do",
             "what", "how", "if", "and", "on", "in", "it", "am", "i", "while"}


def _tokenize(text: str):
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# ---------- Shared agent loop ----------
#
# Every agent below (both specialists and the supervisor) runs the same loop,
# so the tool-use protocol is implemented once and correctly:
#
#   1. The model can return SEVERAL tool_use blocks in one turn (parallel tool
#      use). The API requires a matching tool_result for EVERY one of them in
#      the very next user message — handling only the first is a 400.
#   2. After feeding results back the model may want to call tools again, so
#      this loops rather than making a single follow-up call.
#   3. The final turn may contain thinking + text blocks, so collect text
#      blocks rather than assuming content[0].text.

MAX_TOOL_TURNS = 4  # cap so a confused agent can't spin forever


def _text_blocks(response) -> str:
    """All text blocks joined. `next(b.text for b in ...)` raises StopIteration
    when a turn contains only thinking/tool_use blocks."""
    return "\n\n".join(b.text for b in response.content if b.type == "text").strip()


def run_agent_loop(system: str, messages: list, tools: list,
                   handlers: dict, max_tokens: int = 700) -> str:
    """Drive one agent until it produces a final text reply."""
    for _ in range(MAX_TOOL_TURNS):
        response = client.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            tools=tools, messages=messages,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            return _text_blocks(response) or "(the model returned no text)"

        # Append the assistant turn verbatim — thinking blocks included.
        messages.append({"role": "assistant", "content": response.content})

        results = []
        for tool_use in tool_uses:
            handler = handlers.get(tool_use.name)
            if handler is None:
                output = {"error": f"no handler registered for tool '{tool_use.name}'"}
            else:
                try:
                    output = handler(**tool_use.input)
                except Exception as exc:
                    # A tool crash must still come back as a tool_result, or the
                    # conversation is left in an unsendable state.
                    output = {"error": f"{type(exc).__name__}: {exc}"}
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": output if isinstance(output, str) else json.dumps(output),
            })

        messages.append({"role": "user", "content": results})

    return "(agent hit the tool-call limit without producing a final reply)"


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

    return run_agent_loop(
        system,
        [{"role": "user", "content": customer_message}],
        [GET_CLAIM_STATUS_TOOL],
        {"get_claim_status": get_claim_status},
    )


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

    return run_agent_loop(
        system,
        [{"role": "user", "content": customer_message}],
        [SEARCH_POLICY_TOOL],
        {"search_policy": search_policy},
    )


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
    # The bridge between the two levels. From run_agent_loop's perspective
    # this is an ordinary tool handler: string in, string out. Inside, it runs
    # an entire agent with its own loop and its own tools. That symmetry is
    # what makes the pattern compose — a specialist could itself delegate
    # further and nothing above would need to know.
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
    return run_agent_loop(
        SUPERVISOR_SYSTEM,
        [{"role": "user", "content": customer_message}],
        [HANDOFF_TOOL],
        {"handoff": execute_handoff},
    )


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
    """The output contract for assist mode.

    requires_human_approval defaults to True and is never assigned anywhere in
    this file. A field that can only ever hold one value isn't a variable —
    it's a guarantee the type system makes on your behalf. There is no code
    path that produces a payload claiming it can skip review.
    """
    recommended_response: str = Field(description="Draft reply a human agent could send as-is or edit")
    proposed_specialist: Optional[str] = Field(default=None, description="Which specialist was consulted, if any")
    proposed_task: Optional[str] = Field(default=None, description="The task passed to that specialist, if any")
    requires_human_approval: bool = Field(default=True, description="Always True — nothing reaches the customer automatically")


def run_supervisor_agent_assist(customer_message: str) -> AgentAssistPayload:
    # Same routing as run_supervisor; we just record what got handed off so the
    # human reviewer can see which specialist produced the draft.
    handoffs = []

    def record_handoff(specialist: str, task: str) -> str:
        handoffs.append((specialist, task))
        return execute_handoff(specialist, task)

    draft = run_agent_loop(
        SUPERVISOR_SYSTEM,
        [{"role": "user", "content": customer_message}],
        [HANDOFF_TOOL],
        {"handoff": record_handoff},
    )

    return AgentAssistPayload(
        recommended_response=draft,
        # Stay None when no handoff happened (e.g. a greeting); join if the
        # supervisor consulted more than one specialist.
        proposed_specialist=", ".join(s for s, _ in handoffs) or None,
        proposed_task=" | ".join(t for _, t in handoffs) or None,
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
