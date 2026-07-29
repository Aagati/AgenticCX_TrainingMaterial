"""
PM · H1 — Insurance Supervisor + 2 Specialist Agents (STARTER)

This is AM · H2 with the routing upgraded twice over.

This morning the supervisor was a classifier: one word out, an if/else picked
a specialist, done. Here the supervisor is an AGENT that decides for itself
whether a specialist is needed at all — "Hi there!" should get answered
directly, not routed. And the specialists are no longer given all the data up
front; each has a TOOL and fetches what it needs.

That means three agents (claims, policy, supervisor) each running a tool-use
loop, and the supervisor's "tool" is an entire sub-agent. The specialist's
reply comes back as a tool_result like any other, which is the whole trick:
to the supervisor, delegating to another agent looks exactly like calling a
function.

The loop mechanics are PROVIDED below as run_agent_loop() — including the
parallel-tool_use handling (one turn can contain several tool_use blocks; the
API requires a tool_result for every one of them, not just the first) and the
"final turn may have no text block" handling. That part is infrastructure,
not the lesson. Your TODOs are the agent-specific pieces: each specialist's
system prompt + tools + handler, wired into the shared loop.

Part 2 then reuses all of it unchanged and only alters the last step.

Run: `python starter.py` — paths resolve relative to this file, so any
working directory is fine.
"""

import json
import os
import re
import sys
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

# Windows consoles default to cp1252 and crash when the model emits an arrow,
# em-dash or curly quote. Force UTF-8 so a print() cannot kill the lab.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = Anthropic()
MODEL = "claude-sonnet-5"

# Resolve data next to THIS file, so the lab runs from any working directory.
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DATA_DIR, "claims_data.json")) as f:
    CLAIMS = json.load(f)
with open(os.path.join(DATA_DIR, "policy_clauses.json")) as f:
    POLICY_CLAUSES = json.load(f)

STOPWORDS = {"the", "is", "a", "an", "of", "to", "for", "my", "does", "do",
             "what", "how", "if", "and", "on", "in", "it", "am", "i", "while"}


def _tokenize(text: str):
    """Provided — same helper you had in Day 1's H1 lab. Use it in TODO 2
    below instead of writing another tokenizer from scratch."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# ---------- Shared agent loop (provided) ----------
#
# Every agent below (both specialists and the supervisor) runs this same
# loop, so the tool-use protocol only has to be gotten right once:
#
#   1. The model can return SEVERAL tool_use blocks in one turn (parallel
#      tool use). The API requires a matching tool_result for EVERY one of
#      them in the very next user message — handling only the first is a 400.
#   2. After feeding results back the model may want to call tools again, so
#      this loops rather than making a single follow-up call.
#   3. The final turn may contain thinking + text blocks, so collect text
#      blocks rather than assuming content[0].text (a bare
#      next(b.text for b in response.content if b.type == "text") raises
#      StopIteration when the turn is thinking + tool_use only).

MAX_TOOL_TURNS = 4  # cap so a confused agent can't spin forever


def _text_blocks(response) -> str:
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
                    # A tool crash must still come back as a tool_result, or
                    # the conversation is left in an unsendable state.
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
    """
    TODO 1: Write a system prompt for the Claims Specialist — empathetic,
    status/next-step focused, has get_claim_status available and should ask
    for a claim id if none was given. Then call run_agent_loop() with that
    system prompt, a starting user message of customer_message,
    tools=[GET_CLAIM_STATUS_TOOL], and handlers={"get_claim_status":
    get_claim_status}. Return what run_agent_loop() returns.
    """
    system_prompt = """
        You are Claims Specialist for an insurance company.
        You are empathetic and focused on providing claims statuses and next steps.
        Use `get_claim_status` tool to look up the status, filed date, and next step for a claim by id.
        If no claim id is provided, ask the user for it."""

    return run_agent_loop(
        system_prompt,
        messages=[{"role": "user", "content": customer_message}],
        tools=[GET_CLAIM_STATUS_TOOL],
        handlers={"get_claim_status": get_claim_status},
        #max_tokens=500
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
    """
    TODO 2: Keyword overlap retrieval over POLICY_CLAUSES using the provided
    _tokenize() — same technique as Day 1's H1 lab. For each clause, tokenize
    its title + text, score it by the size of the overlap with the
    tokenized query, and return the top 2 scoring clauses (score > 0) as a
    list of {id, title, text} dicts.
    """
    q_tokens = set(_tokenize(query))
    scored=[]
    for c in POLICY_CLAUSES:
        c_tokens = set(_tokenize(c['title'] + ' ' + c['text']))
        score = len(q_tokens.intersection(c_tokens))
        scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in scored[:2] if score > 0] 


def run_policy_specialist(customer_message: str) -> str:
    """
    TODO 3: Write a system prompt for the Policy Specialist — precise,
    citation-oriented, must use search_policy and answer ONLY from returned
    clauses, citing ids (e.g. [POL-010]) for every factual claim, and should
    say it doesn't have the information if nothing relevant is found. Then
    call run_agent_loop() the same way as TODO 1, with
    tools=[SEARCH_POLICY_TOOL] and handlers={"search_policy": search_policy}.

    Heads-up: this agent in particular tends to fire two search_policy calls
    in one turn (parallel tool use) — run_agent_loop() already handles that,
    which is the whole point of using it instead of hand-rolling the loop
    again here.
    """
    system_prompt = """
        You are a Policy Specialist for an insurance company.
        You are precise and citation-oriented, and must use `search_policy` to answer questions about policy clauses.
        Answer ONLY from the returned clauses, citing ids (e.g. [POL-010]) for every factual claim.
        If nothing relevant is found, say you don't have the information."""

    return run_agent_loop(
        system_prompt,
        messages=[{"role": "user", "content": customer_message}],
        tools=[SEARCH_POLICY_TOOL],
        handlers={"search_policy": search_policy},
        #max_tokens=500
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
    if specialist == "claims":
        return run_claims_specialist(task)
    elif specialist == "policy":
        return run_policy_specialist(task)
    return "Unknown specialist."


SUPERVISOR_SYSTEM = """
You are a front-line Supervisor for an Insurance CX system.
For claim status/filing questions -> hand off to the "claims" specialist.
For coverage/policy wording questions -> hand off to the "policy" specialist.
For greetings, thanks, or anything that does not require the expertise of the specialist, just respond directly yourself - NO HANDOFF unless required

When you perform a hand-off, pass the customer's actual question as the task."""


def run_supervisor(customer_message: str) -> str:
    """
    TODO 4b: Write the Supervisor's system prompt — decide whether this needs
    a specialist handoff (claims or policy) or can be handled directly (e.g.
    greetings, thanks), using the handoff tool when appropriate and relaying
    the specialist's answer back to the customer in a consistent voice.

    Assign it to the SUPERVISOR_SYSTEM constant above (not inline in this
    function) — TODO 6 reuses the exact same prompt for agent-assist mode,
    and a module-level constant means it can't drift out of sync between the
    two call sites.

    Then call run_agent_loop() with system=SUPERVISOR_SYSTEM,
    tools=[HANDOFF_TOOL], and handlers={"handoff": execute_handoff}.

    The interesting case is the one with NO tool call. "Hi there!" must be
    answered directly — an agent that routes a greeting to the claims
    specialist is worse than the morning's classifier, which at least was
    fast. Say so explicitly in the system prompt; left to itself, a model
    holding a shiny tool will reach for it.
    """
    return run_agent_loop(
        SUPERVISOR_SYSTEM,
        [{"role": "user", "content": customer_message}],
        [HANDOFF_TOOL],
        {"handoff": execute_handoff}
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


# ============================================================
# Part 2 — Agent-Assist Mode (required)
# ============================================================
#
# Same routing, same specialists, same research. ONE thing changes: the final
# reply is returned as a reviewable payload instead of being sent.
#
# The point is how little has to change. If autonomy level is a property of
# the last step rather than of the architecture, you can ship a new flow in
# assist mode, watch humans approve or edit the drafts for a few weeks, and
# flip it to autonomous once the edit rate is low — without a rewrite. Systems
# that hardcode "send" throughout can't make that move.
#
# requires_human_approval defaults to True and is never computed. A field that
# can only ever be True is a contract, not a variable.
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
    recommended_response: str = Field(description="Draft reply a human agent could send as-is or edit")
    proposed_specialist: Optional[str] = Field(default=None, description="Which specialist was consulted if any were used in the Support.")
    proposed_task: Optional[str] = Field(default=None, description="tasks passed to the specialist if any were used in the support")
    required_human_approval: bool = Field(default=True, description="Always True - Nothing should reach the customer automatically")


def run_supervisor_agent_assist(customer_message: str) -> AgentAssistPayload:
    """
    TODO 6: Same routing as run_supervisor (TODO 4) — reuse the
    SUPERVISOR_SYSTEM constant, don't rewrite the prompt — but you need to
    know WHICH specialist(s) got consulted to fill in the payload, and
    execute_handoff() itself only returns a string. Wrap it: define a local
    record_handoff(specialist, task) that appends (specialist, task) to a
    list and then calls execute_handoff(specialist, task), and pass
    {"handoff": record_handoff} as the handlers dict instead of
    execute_handoff directly.

    Then:
      - if no handoff happened, return AgentAssistPayload(recommended_response=<text>)
      - if a handoff happened, return AgentAssistPayload with
        recommended_response=<final draft text>, proposed_specialist=<which
        one(s)>, proposed_task=<the task string(s) used>
    Nothing should be printed to "the customer" — this function only ever
    returns a payload for a human to review.
    """
    handoffs = []

    def record_handoff(specialist, task: str) -> str:
        handoffs.append((specialist, task))

    draft = run_agent_loop(
        SUPERVISOR_SYSTEM,
        [{"role": "user", "content": customer_message}],
        [HANDOFF_TOOL],
        {"handoff": record_handoff}
    )

    return AgentAssistPayload(
        recommended_response=draft, 
        proposed_specialist="".join(s for s, _ in handoffs) or None,
        proposed_task=" | ".join(t for _, t in handoffs) or None
    )


if __name__ == "__main__":
    print("\n\n=== Part 2: Agent-Assist Mode ===")
    for m in test_messages:
        print(f"\nCUSTOMER: {m}")
        payload = run_supervisor_agent_assist(m)
        print(payload.model_dump_json(indent=2))
