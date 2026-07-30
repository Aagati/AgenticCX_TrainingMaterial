# PM · H1 — Banking: Idempotent, Audited Transactional Action via MCP

**Track:** Banking | **Time box:** ~55 min (Part A ~35 min, Part B ~20 min) | **Ships:** a safe, audited, real-MCP action
**Pattern practiced:** idempotency keys + append-only audit logging around a real transactional MCP tool

## Scenario
This morning's H1 built a ticketing tool over real MCP — read/write, but
not money-moving. This afternoon you build the real thing: `process_refund`,
a transactional action that moves money, served the same way over the same
protocol. Two production concerns that didn't matter for a ticket matter
enormously here: **idempotency** (if the network hiccups and the client
retries the same request, the customer must NOT be refunded twice) and
**audit logging** (every execution of a money-moving action needs a
permanent, attributable record).

Both concerns live in the **server**, not the client — deliberately. A
network retry re-invokes the external system (this server), not whichever
agent process happened to be running when the first attempt was made. Put
`PROCESSED_KEYS` in the agent's memory instead and a *second* agent
process, or a redeployed one, would happily refund the same transaction
again — the dedup would only ever protect against retries from the exact
process that made the first call.

---

## Part A — Build the refund server
`server_starter.py` → `server_solution.py`

Same `@mcp.tool()` / stdio-transport shape as `AM_H1a` — what's new is the
logic inside the tool, not the protocol around it.

**Your task**
1. `audit_log(actor, action, details, result)` — append a structured entry
   (timestamp, actor, action, details, result) to `AUDIT_LOG`.
2. `process_refund(transaction_id, amount, idempotency_key)` — before doing
   anything, check whether `idempotency_key` has been seen before
   (`PROCESSED_KEYS`, a dict of `idempotency_key -> result`). If so,
   `audit_log` the replay and return the SAME result as the original call
   without processing anything again. If not, process the refund (append
   to `REFUND_LEDGER`), store the result under that idempotency_key,
   `audit_log` the fresh processing, and return the result.

`get_ledger()` / `get_audit_log()` are given — two more `@mcp.tool()`s that
just return the module-level lists. They exist because Part B is a
*different process*: it can't `import server_starter` and read
`REFUND_LEDGER` directly, it has to ask over the protocol like anything
else this server exposes.

**Verify it standalone** (no client, no LLM, no cost) — drop into a REPL
and call `process_refund(...)` directly as a plain Python function twice
with the same `idempotency_key`, confirm `REFUND_LEDGER` only grew once
and `AUDIT_LOG` grew twice.

---

## Part B — Simulate a retry through the real client
`client_starter.py` → `client_solution.py`

The spawn/discover/call_tool mechanics here are the same ones you built in
`AM_H1b` — given as working boilerplate. The one new piece: after the model
processes the refund once, simulate a network-layer retry by calling
`process_refund` a **second time directly** (bypassing the model entirely
— this is what a raw HTTP client retry looks like) with the exact same
`transaction_id`/`amount`/`idempotency_key` the model used.

**Your task**
- Inside `main()`, after the first `run_turn()` call: call
  `await session.call_tool("process_refund", used_args)` again with the
  args captured from the model's first call, print the raw result, and
  confirm it's identical to the first call's result.

Run it and confirm: `get_ledger()` still shows exactly ONE entry;
`get_audit_log()` shows TWO — `"process_refund"` then
`"process_refund_replay"` — both attributed and timestamped.

```bash
pip install anthropic mcp
export ANTHROPIC_API_KEY=sk-...
python client_starter.py
```
(Uses this repo's root `.env` via `load_dotenv()` — no new key needed if
it's already set there.)

## What "ships" means
By the end you should be able to run `client_starter.py` and demonstrate,
with printed output: one real refund processed over MCP, a simulated
retry that is correctly deduplicated by the SERVER (not by client-side
bookkeeping), and a complete audit trail covering both calls, fetched
back over the protocol.

## Files
- `server_starter.py` / `server_solution.py` — Part A, the refund server:
  `process_refund` + idempotency + audit log.
- `client_starter.py` / `client_solution.py` — Part B, the MCP client +
  retry simulation. `client_starter.py` spawns `server_starter.py` (Part
  A's own output); `client_solution.py` spawns `server_solution.py`, so
  it's runnable standalone as a reference regardless of Part A's state.

## Stretch goals
- Add a `max_amount` guardrail to `process_refund` itself: refuse (and
  `audit_log` the refusal) any amount above a threshold, regardless of
  what the model requests — connects directly to Day 1's confirmation-gate
  guardrail and `AM_H3`'s code-level permission gate, applied here to a
  dollar amount instead of ownership.
- Make the audit log replayable: write a function that takes
  `AUDIT_LOG`/`get_audit_log()`'s output and reconstructs a human-readable
  narrative of exactly what happened, in order — this previews `PM_H2`'s
  audit trail work.
- Two DIFFERENT customers' refunds interleaved in the same run — confirm
  `PROCESSED_KEYS` (global on the server, not scoped per customer) never
  cross-matches one customer's idempotency key against another's request.

## Discussion (bring back to the group)
- Where should the idempotency key come from in a real system — the
  client (customer's device/session), your API layer, or the model? What
  goes wrong if the model is allowed to generate a fresh key on every
  retry instead of reusing one?
- `process_refund`'s idempotency lives in the MCP server, not the agent
  process. What would break if it lived in the agent instead — walk
  through what happens on a redeploy of the agent mid-retry-window.
