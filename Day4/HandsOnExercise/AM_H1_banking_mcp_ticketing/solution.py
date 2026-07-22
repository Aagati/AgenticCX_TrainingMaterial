"""
AM · H1 — Banking: MCP Ticketing Integration (REFERENCE SOLUTION)
"""

import json
import uuid
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

TICKET_STORE = {}

CREATE_TICKET_TOOL = {
    "name": "create_ticket",
    "description": "Create a support ticket in the ticketing system.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["subject", "description", "priority"],
    },
}

RESOLVE_TICKET_TOOL = {
    "name": "resolve_ticket",
    "description": "Mark a ticket as resolved with a resolution note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "resolution_note": {"type": "string"},
        },
        "required": ["ticket_id", "resolution_note"],
    },
}

TOOLS = [CREATE_TICKET_TOOL, RESOLVE_TICKET_TOOL]

SYSTEM_PROMPT = """You are a banking support agent. When a customer reports
an issue that needs follow-up, use create_ticket with a clear subject,
description, and appropriate priority. Tell the customer their ticket
number. If a later message confirms the issue is resolved, use
resolve_ticket with a brief resolution note."""


def create_ticket(subject: str, description: str, priority: str) -> dict:
    ticket_id = f"TCK-{uuid.uuid4().hex[:6].upper()}"
    TICKET_STORE[ticket_id] = {
        "subject": subject, "description": description, "priority": priority,
        "status": "open", "resolution_note": None,
    }
    return {"ticket_id": ticket_id, "status": "open"}


def resolve_ticket(ticket_id: str, resolution_note: str) -> dict:
    if ticket_id not in TICKET_STORE:
        return {"error": "ticket not found"}
    TICKET_STORE[ticket_id]["status"] = "resolved"
    TICKET_STORE[ticket_id]["resolution_note"] = resolution_note
    return {"ticket_id": ticket_id, "status": "resolved"}


TOOL_FUNCS = {"create_ticket": create_ticket, "resolve_ticket": resolve_ticket}


def run_turn(messages: list) -> list:
    response = client.messages.create(
        model=MODEL, max_tokens=400, system=SYSTEM_PROMPT,
        tools=TOOLS, messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use is None:
        text = next(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": text})
        return messages

    func = TOOL_FUNCS[tool_use.name]
    result = func(**tool_use.input)

    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
    ]})

    followup = client.messages.create(
        model=MODEL, max_tokens=300, system=SYSTEM_PROMPT,
        tools=TOOLS, messages=messages,
    )
    text = next(b.text for b in followup.content if b.type == "text")
    messages.append({"role": "assistant", "content": text})
    return messages


if __name__ == "__main__":
    convo = [{"role": "user", "content": "My transfer to my landlord failed and the money hasn't come back yet."}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    convo.append({"role": "user", "content": "Update — the money just came back on its own, you can close it out."})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    print("\n[TICKET_STORE]:", json.dumps(TICKET_STORE, indent=2))

# Expected: turn 1 creates a ticket (status "open") and tells the customer
# a ticket number. Turn 2 calls resolve_ticket on that same ticket_id,
# TICKET_STORE shows status "resolved" with a resolution_note.
