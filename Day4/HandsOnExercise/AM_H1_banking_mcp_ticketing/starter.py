"""
AM · H1 — Banking: MCP Ticketing Integration (STARTER)
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
    """
    TODO 1: Generate a ticket_id (e.g. f"TCK-{uuid.uuid4().hex[:6].upper()}"),
    store a dict with subject, description, priority, status="open",
    resolution_note=None in TICKET_STORE[ticket_id], and return
    {"ticket_id": ticket_id, "status": "open"}.
    """
    raise NotImplementedError


def resolve_ticket(ticket_id: str, resolution_note: str) -> dict:
    """
    TODO 2: If ticket_id not in TICKET_STORE, return {"error": "ticket not found"}.
    Otherwise set status="resolved" and resolution_note, then return
    {"ticket_id": ticket_id, "status": "resolved"}.
    """
    raise NotImplementedError


TOOL_FUNCS = {"create_ticket": create_ticket, "resolve_ticket": resolve_ticket}


def run_turn(messages: list) -> list:
    """
    TODO 3: Standard tool-use loop (same shape as Day 1/2/3 labs):
      - call the model with tools=TOOLS
      - if it calls a tool, execute via TOOL_FUNCS, feed the result back,
        get a follow-up reply
      - append the assistant's final text reply to `messages` and return it
    """
    raise NotImplementedError


if __name__ == "__main__":
    convo = [{"role": "user", "content": "My transfer to my landlord failed and the money hasn't come back yet."}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    convo.append({"role": "user", "content": "Update — the money just came back on its own, you can close it out."})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    print("\n[TICKET_STORE]:", json.dumps(TICKET_STORE, indent=2))
