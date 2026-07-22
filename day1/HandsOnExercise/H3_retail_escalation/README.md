# H3 — Retail: Escalation with Full Context Handoff

**Track:** Retail | **Time box:** 20-30 min (capstone — combines H1 + H2 patterns) | **Pattern practiced:** confirm → escalate with context, not a cold transfer

## Scenario
A customer is disputing a charge on an order and is getting frustrated — the
order was never delivered but they were still billed, and now they're asking
for a refund the agent isn't authorized to issue automatically. Instead of
the classic bad experience ("let me transfer you, please repeat everything
to the next person"), the agent should recognize this is outside its
authority and **package up the full conversation + relevant facts into a
structured handoff** for a human agent — so the customer never has to
re-explain themselves.

## Your task
Build an `escalate_to_human(summary, customer_sentiment, order_id,
requested_action, conversation_transcript)` tool and an agent that:
1. Tries to resolve the issue itself first (e.g., can look up order status
   via a stubbed `get_order_status(order_id)` tool).
2. Recognizes when a request is outside its authority — refunds above a
   threshold, or the customer explicitly asks for a human/supervisor — and
   decides to escalate rather than keep trying or make something up.
3. Calls `escalate_to_human` with a **complete context package**: what
   happened, what the customer wants, sentiment/urgency, and the full
   transcript — not just "customer is upset, please help."
4. Tells the customer, in plain language, that they're being connected to a
   specialist and that specialist already has the full context (so the
   customer doesn't need to repeat themselves).

## Why this matters
This ties together the whole morning:
- **Topic 03 (agentic loop):** escalation is a legitimate terminal action of
  the loop, not a failure of it.
- **Topic 05 (human-in-the-loop):** the quality bar for escalation isn't
  "did it escalate" — it's "did it hand off enough context that the human
  doesn't waste the customer's time re-asking questions the agent already
  had answers to."
- **Topic 06 (guardrails):** authority limits (e.g., refund thresholds) are
  guardrails the agent must respect, and hitting one is itself a trigger for
  escalation — not something to route around.

## Files
- `starter.py` — scaffold with TODOs, stub `get_order_status` and
  `escalate_to_human` tools.
- `solution.py` — reference solution.

## A note on the handoff payload
`escalate_to_human`'s schema comes from a **Pydantic model**
(`EscalationPayload`), with a validator that rejects empty fields AND
common placeholder values ("TBD", "N/A", "UNKNOWN") — the most common way
a "complete-looking" handoff actually fails to be complete. A malformed or
placeholder-filled handoff is rejected outright rather than creating a
ticket that looks fine to a human agent but isn't.

## Setup
```bash
pip install anthropic pydantic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a second escalation trigger: 3+ back-and-forth turns without
  resolution should also trigger escalation, even if the customer never
  explicitly asks for a human.
- Score the quality of the handoff package yourself: would a human agent
  reading only `summary` + `requested_action` (without the full transcript)
  have enough to act in under 10 seconds? If not, tighten the prompt.

## Wrap-up discussion (whole class, before lunch)
Across H1 → H2 → H3, the tool the agent has access to changed the guardrail
needed: read-only (H1, no gate) → irreversible single action (H2, confirm
before executing) → out-of-authority (H3, escalate instead of executing).
This is the mental model to carry into this afternoon's guardrails deep
dive.
