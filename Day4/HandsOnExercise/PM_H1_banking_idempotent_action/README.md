# PM · H1 — Banking: Idempotent, Audited Transactional Action via MCP

**Track:** Banking | **Time box:** ~70 min | **Ships:** a safe, audited action
**Pattern practiced:** idempotency keys + append-only audit logging around a real transactional tool

## Scenario
This morning's H1 built a ticketing tool — read/write, but not money-moving.
This afternoon you build the real thing: `process_refund`, a transactional
action that moves money. Two production concerns that didn't matter for a
ticket matter enormously here: **idempotency** (if the network hiccups and
the client retries the same request, the customer must NOT be refunded
twice) and **audit logging** (every execution of a money-moving action
needs a permanent, attributable record).

## Your task
1. `process_refund(transaction_id, amount, idempotency_key)` — before
   doing anything, check whether `idempotency_key` has been seen before
   (`PROCESSED_KEYS`, a dict of `idempotency_key -> result`). If so, return
   the SAME result as the original call without processing anything again.
   If not, process the refund (append to `REFUND_LEDGER`), store the
   result under that idempotency_key, and return it.
2. `audit_log(actor, action, details, result)` — append a structured entry
   (timestamp, actor, action, details, result) to `AUDIT_LOG`. Call this
   from inside `process_refund` for EVERY call — including idempotent
   replays (log that it was a replay, don't just silently skip logging).
3. An agent loop with a `process_refund` tool where the model generates a
   fresh idempotency key per NEW customer request, but you (not the model)
   are responsible for demonstrating what happens on a retry: call
   `process_refund` a second time with the SAME transaction_id, amount,
   AND idempotency_key (simulating a network retry) and confirm the
   refund is NOT double-processed.
4. Print the final `REFUND_LEDGER` (should show exactly one refund) and
   `AUDIT_LOG` (should show two entries — original + replay — both
   attributed and timestamped).

## What "ships" means
By the end you should be able to run your build and demonstrate, with
printed output: one real refund processed, a simulated retry that is
correctly deduplicated, and a complete audit trail covering both calls.

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
- Add a `max_amount` guardrail: `process_refund` should refuse (and audit
  log the refusal) any amount above a threshold, regardless of what the
  model requests — this connects directly to Day 1's confirmation-gate
  guardrail and this morning's Topic 02 (action design, transactional
  safety).
- Make the audit log replayable: write a function that takes `AUDIT_LOG`
  and reconstructs a human-readable narrative of exactly what happened, in
  order — this previews PM·H2's audit trail work.

## Discussion (bring back to the group)
- Where should the idempotency key come from in a real system — the
  client (customer's device/session), your API layer, or the model? What
  goes wrong if the model is allowed to generate a fresh key on every
  retry instead of reusing one?
