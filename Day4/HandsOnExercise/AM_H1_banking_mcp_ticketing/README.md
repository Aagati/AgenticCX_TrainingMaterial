# AM · H1 — Banking: Connect the Agent to a Ticketing System via MCP

**Track:** Banking | **Time box:** ~55 min (Part A ~25 min, Part B ~30 min) | **Pattern practiced:** building and consuming a real MCP server

## A note on this lab
Earlier drafts of this lab simulated the ticketing system with an in-process
Python dict and skipped MCP entirely — the reasoning being "no real
Zendesk/ServiceNow instance for the whole cohort." That's true, but the MCP
*protocol* doesn't need a real Zendesk account to be real: `server_starter.py`
is a genuine, separate OS process speaking the real MCP protocol (stdio
transport, official `mcp` SDK) with a mocked backend behind it. The protocol
boundary — the part this curriculum can actually teach without a trainee's
own SaaS credentials — is real; only the account behind it isn't. This lab
is now two parts, each with its own starter/solution, so you build both
sides of that boundary instead of just reading about one of them.

## Scenario
A banking customer messages in: "My transfer to my landlord failed and the
money hasn't come back yet." This needs a real ticket in the support
system — not just a chat reply — so a human can follow up if the agent's
answer isn't enough.

---

## Part A — Build an MCP server
`server_starter.py` → `server_solution.py`

Build the ticketing system itself as a standalone MCP server: a separate
process, launched over stdio, that any MCP-compatible client can discover
and call.

**Your task**
1. `create_ticket(subject, description, priority)` — creates a ticket in
   `TICKET_STORE`, returns a generated `ticket_id`.
2. `resolve_ticket(ticket_id, resolution_note)` — marks a ticket resolved
   with a note. Returns an error if `ticket_id` doesn't exist.

Both are registered with `@mcp.tool()` — FastMCP derives the JSON schema
the client sees from the function's type hints **and its docstring**, so
the docstring isn't optional decoration here, it's part of the tool's
public contract. Don't touch it; fill in the bodies.

**Verify it standalone** (no client, no LLM, no cost):
```bash
python server_starter.py
```
This blocks, serving over stdio — Ctrl+C to stop. To actually exercise the
logic without a client yet, drop into a REPL and call `create_ticket(...)`
/ `resolve_ticket(...)` directly as plain Python functions (the `@mcp.tool()`
decorator doesn't stop you calling them locally) — confirm `TICKET_STORE`
updates and `resolve_ticket` on an unknown id returns the error dict, not
a crash.

---

## Part B — Use an MCP server
`client_starter.py` → `client_solution.py`

Now build the agent side: spawn `server_starter.py` as a subprocess,
discover its tools over the real MCP protocol (no hardcoded schema — the
server is the only source of truth), and drive a two-turn conversation
through it.

**Your task**
1. `mcp_tool_to_anthropic_schema()` — map an MCP tool object onto the dict
   shape Anthropic's `tools=[...]` expects.
2. Inside `run_turn()` — call the tool over MCP with
   `session.call_tool(...)` and extract the result text.
3. Inside `main()` — set up `StdioServerParameters` and open the
   `stdio_client` / `ClientSession` pair that spawns and talks to
   `server_starter.py`.

Run both turns and confirm the printed `[Discovered ... tools over MCP]`
line lists `create_ticket`/`resolve_ticket`, then that the conversation
shows the ticket created and resolved — proof the round trip crossed a
real process boundary, not just a Python function call.

```bash
pip install anthropic mcp
export ANTHROPIC_API_KEY=sk-...
python client_starter.py
```
(Uses this repo's root `.env` via `load_dotenv()` — no new key needed if
it's already set there.)

## Why this matters
This is today's Topic 01 (enterprise integration) and Topic 02 (action
design — typed tools) made concrete, and it's the same typed-tool contract
every other Day 1-3 lab used — MCP just adds a standard transport and
discovery protocol on top of it, so any MCP-compatible agent can find and
call `create_ticket` without custom integration code per agent. Part A
proves you can author that contract; Part B proves you can consume one you
didn't write (`client_starter.py` never hardcodes `create_ticket`'s
schema — it asks the server).

## Files
- `server_starter.py` / `server_solution.py` — Part A, the MCP server.
- `client_starter.py` / `client_solution.py` — Part B, the MCP client +
  agent loop. Spawns `server_starter.py` (Part A's own output) as its
  subprocess — `client_solution.py` spawns `server_solution.py` instead,
  so it's runnable standalone as a reference regardless of Part A's state.

## Stretch goals
- Add a third tool, `add_ticket_comment(ticket_id, comment)`, to the
  server, and have the client's agent use it if the customer provides more
  detail before the ticket is resolved.
- Reject a `create_ticket` call where `priority` isn't one of `"low"`,
  `"medium"`, `"high"` — since FastMCP derives the schema from type hints
  rather than a hand-written JSON `enum`, this needs an explicit check
  inside the tool body — and see how the model responds when the tool
  result is a validation error instead of a crash.
- Run `server_solution.py` standalone and point an MCP inspector or
  Claude Desktop's MCP config at it directly, with no Python client code
  of your own — the point of the protocol being the contract.

## Discussion (bring back to the group)
- What's the difference in blast radius between a tool with a typed enum
  parameter (`priority`) and one that took a free-text priority string?
  Where else in today's other labs would you want to apply that same
  narrowing?
- Part A and Part B are two separate OS processes with two independent
  `TICKET_STORE` dicts that happen to share a class definition but share
  zero memory. What would go wrong if you tried to inspect Part A's
  in-process `TICKET_STORE` right after running Part B's client and
  expected to see the ticket it just created?
