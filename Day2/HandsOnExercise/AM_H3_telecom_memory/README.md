# AM · H3 — Telecom: Cross-Session Memory

**Track:** Telecom | **Time box:** 20 min | **Pattern practiced:** persist durable facts → recall on the next session, without re-asking

## Scenario
A customer calls telecom support today about slow data speeds. They mention
their device is an iPhone 15 and their plan is "Unlimited Plus." Tomorrow,
they message in again about a billing question. A good agent doesn't make
them repeat their device and plan — it already knows.

## Your task
Build a tiny persistent memory layer:
1. `save_fact(customer_id, key, value)` — writes a durable fact to a JSON
   file acting as your "database" (`memory_store.json`), keyed by customer.
2. `load_profile(customer_id)` — reads all known facts for a customer.
3. `extract_facts(message)` — a narrow Claude call that pulls out any
   durable profile facts mentioned in a message (device model, plan name,
   preferred contact method — NOT one-off details like "my data is slow
   today," which is session-specific, not durable).
4. A `chat(customer_id, message)` function that: loads the existing
   profile, injects it into the system prompt ("known facts about this
   customer: ..."), gets a reply, then extracts and saves any new facts
   from the customer's message for next time.

Run two separate "sessions" (just two separate calls to `chat()` in your
`__main__` block, simulating the customer coming back on a different day)
and confirm the second session's system prompt already includes facts
learned in the first, without the customer restating them.

## Why this matters
This is today's Topic 05 (persistent memory): cross-session memory is what
lets "don't make the customer repeat themselves" hold true not just within
one conversation (which any agent with a message history does for free) but
across separate sessions, days, and — as of this afternoon's Applied Lab —
across channels too.

## Files
- `starter.py` — scaffold with TODOs. Creates `memory_store.json` on first run.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a `confidence` or `source` field to each saved fact (e.g. "customer
  stated" vs. "inferred") so a future agent can decide whether to state a
  fact back confidently or double check it.
- Add a simple expiry: a fact like "currently has a service outage in area"
  should not persist forever the way "device model" should.

## Discussion (bring back to the group)
- What's the risk of saving *too much* to durable memory — e.g. saving "the
  customer was frustrated today" as if it were a permanent trait? Where's
  the line between session-specific and durable?

---

## Alt-stack variant (optional)
`solution_crewai.py` — same cross-session memory task, using CrewAI's
built-in `memory=True` instead of solution.py's hand-rolled
extract_facts()/JSON-store. Needs `OPENAI_API_KEY` too (CrewAI's long-term
memory embeds facts via OpenAI by default). See `requirements-multisdk.txt`.
