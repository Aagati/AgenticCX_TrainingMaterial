# PM · H2 — Banking: Episodic + Semantic Memory Across Sessions

**Track:** Banking | **Time box:** ~45 min | **Ships:** a memory-enabled CX agent
**Pattern practiced:** two-tier memory architecture — durable profile facts vs. recent session history

## Scenario
This morning (AM · H3) you built one flat memory store: durable facts about
a customer. That's **semantic memory** — stable, general knowledge about
who the customer is ("has an iPhone 15," "prefers email"). Real systems
also need **episodic memory** — a record of *what happened*, session by
session ("on July 15th, disputed a $45 charge; on July 16th, asked about a
late fee"). The two serve different purposes: semantic memory shapes how
the agent talks to the customer; episodic memory lets the agent reference
what was already discussed and avoid contradicting or repeating itself.

## Your task
Build a two-tier memory store (`memory_store.json`, keyed by customer):

```json
{
  "cust_id": {
    "semantic": {"preferred_name": "...", "communication_pref": "..."},
    "episodic": [
      {"date": "2026-07-15", "summary": "Disputed a $45 charge at Green Leaf Grocers, case opened."}
    ]
  }
}
```

1. `save_semantic_fact(customer_id, key, value)` / `load_semantic(customer_id)`
   — same idea as this morning's memory store.
2. `add_episode(customer_id, summary)` — append a dated one-line summary of
   what happened in this session.
3. `load_recent_episodes(customer_id, n=3)` — return the last `n` episode
   summaries.
4. `chat(customer_id, message)` — loads BOTH semantic facts and recent
   episodes, injects both into the system prompt (clearly labeled as two
   different kinds of context), gets a reply, then updates both stores:
   extract any new semantic facts (as this morning), AND write a one-line
   episode summary of this exchange.

Run three sessions in `__main__` to demonstrate: session 1 establishes a
semantic fact and an episode; session 2 references something session 1
discussed (proving episodic recall); session 3 shows both still present.

## Why this matters
This is today's Topic 04 (memory architecture). Conflating episodic and
semantic memory into one blob is a common real-world mistake — it makes the
context window bloat with irrelevant history, and it makes stable facts get
buried or contradicted by transient details. Separating them lets you keep
semantic memory small and durable while episodic memory can be pruned,
summarized, or windowed independently.

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
- Summarize/compress episodes older than N sessions into a single rolled-up
  line instead of keeping every session verbatim forever.
- Add a `topic` tag to each episode (billing, dispute, technical) so
  `load_recent_episodes` can filter by topic instead of just recency.

## Discussion (bring back to the group)
- A customer disputes the same merchant twice in a month. Where does that
  pattern live — semantic ("frequently disputes this merchant") or
  episodic (two separate episode entries)? Does your agent notice the
  pattern, or would a human have to?
