# AM · H1 — Banking: Connect the Agent to a Ticketing System via MCP

**Track:** Banking | **Time box:** ~40 min | **Pattern practiced:** typed tools exposing an enterprise system, create → resolve lifecycle

## A note on this lab's simulation
There's no real Zendesk/ServiceNow instance or MCP server wired up for the
whole cohort — `TICKET_STORE` is an in-memory stand-in for the ticketing
system. **What you build — typed tool schemas the model calls, executed by
your code, with results fed back — is exactly the contract MCP formalizes.**
MCP adds a standard transport and discovery protocol on top of this same
shape (so any MCP-compatible agent can find and call `create_ticket`
without custom integration code per agent), but the tool-call mechanics
you're writing today don't change when you swap in a real MCP server later.

## Scenario
A banking customer messages in: "My transfer to my landlord failed and the
money hasn't come back yet." This needs a real ticket in the support
system — not just a chat reply — so a human can follow up if the agent's
answer isn't enough.

## Your task
Build two typed tools and wire them into an agent:
1. `create_ticket(subject, description, priority)` — creates a ticket in
   `TICKET_STORE`, returns a generated `ticket_id`. `priority` must be one
   of `"low"`, `"medium"`, `"high"`.
2. `resolve_ticket(ticket_id, resolution_note)` — marks a ticket resolved
   with a note. Returns an error if `ticket_id` doesn't exist.
3. An agent loop that: given the customer's message, calls
   `create_ticket` with a sensible subject/description/priority, tells the
   customer their ticket number, and — in a **second, separate** customer
   message confirming the issue is fixed — calls `resolve_ticket`.

Run both turns and confirm `TICKET_STORE` shows the full lifecycle: created
→ resolved, with the resolution note attached.

## Why this matters
This is today's Topic 01 (enterprise integration) and Topic 02 (action
design — typed tools) made concrete. Notice the tool schemas are **typed
and constrained** (priority is an enum, not free text) — this is what
makes an action tool safe to expose to a model: the model can only submit
values your code already knows how to handle correctly.

## Files
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a third tool, `add_ticket_comment(ticket_id, comment)`, and have the
  agent use it if the customer provides more detail before the ticket is
  resolved.
- Reject a `create_ticket` call where `priority` isn't one of the three
  allowed values, and see how the model responds when your code returns a
  validation error as the tool result instead of raising an exception.

## Discussion (bring back to the group)
- What's the difference in blast radius between a tool with a typed enum
  parameter (`priority`) and one that took a free-text priority string?
  Where else in today's other labs would you want to apply that same
  narrowing?

---

## Alt-stack variant (optional)
`mcp_ticket_server.py` + `solution_real_mcp.py` — the "no real MCP server
wired up" caveat above, made real. A standalone MCP server (official `mcp`
SDK, stdio transport) exposes create_ticket/resolve_ticket; the client
discovers and calls them over the actual protocol instead of importing
Python functions directly. Uses your existing `ANTHROPIC_API_KEY` — no new
key needed. See `requirements-multisdk.txt`.
