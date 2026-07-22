# AM · H2 — Insurance: Supervisor Routes to Claims vs. Policy Specialist

**Track:** Insurance | **Time box:** 35 min | **Pattern practiced:** intent classification → route → specialist persona

## Scenario
Your insurance CX agent needs to handle two very different kinds of
questions — "what's covered / what does my policy say" (policy questions)
and "I need to file or check on a claim" (claims questions) — and each
needs a different tone, different scoped knowledge, and different tools.
Rather than one agent trying to be both, today you build the lightweight
version of the pattern: a **supervisor** that classifies intent and routes
to the right **specialist**.

This is the concept-level version of a pattern you'll build in full this
afternoon (Applied Lab H1) with real sub-agent tool calls — today's version
routes in a single Python function, no tool-use loop required yet.

## Your task
Build:
1. A **supervisor classifier** — given the customer's message, classify it
   as `"claims"` or `"policy"` (a single, narrow Claude call, similar in
   spirit to this morning's slot extraction call).
2. Two **specialist system prompts** — a Claims Specialist (empathetic,
   focused on status/next steps, may reference the mock claims data) and a
   Policy Specialist (precise, citation-oriented, grounded in the mock
   policy clauses — reuse the grounding pattern from Day 1 if you want).
3. A `route_and_respond(message)` function that classifies, then calls the
   matching specialist with its own system prompt, and returns the
   specialist's reply along with which specialist handled it (for logging).

## Why this matters
This is today's Topic 03 (multi-agent CX) at its simplest: a supervisor's
only job is to get the right specialist on the line fast — it should be a
narrow, cheap, fast classification, not a heavyweight call. The specialists
stay narrow and scoped, which is what makes each one easy to reason about,
test, and improve independently.

## Files
- `mock_data.json` — a few sample claims and a couple of policy clauses.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a third category, `"other"`, and have the supervisor route anything
  that isn't clearly claims or policy to a generic specialist that asks a
  clarifying question instead of guessing.
- Log every routing decision (message, chosen specialist) to a list and
  print a summary at the end — this is the seed of a routing-accuracy eval.

## Discussion (bring back to the group)
- What happens to response quality and latency if you skip the supervisor
  and just give one agent both specialists' instructions in a single system
  prompt? Try it, and compare.

---

## Alt-stack variant (optional)
`solution_langgraph.py` — the same classify → route → specialist flow,
built as an explicit LangGraph `StateGraph` with a conditional edge instead
of a plain if/else. Uses your existing `ANTHROPIC_API_KEY` via
`langchain-anthropic`. See `requirements-multisdk.txt`.
