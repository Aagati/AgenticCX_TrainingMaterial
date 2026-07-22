# H2 — Banking: Action Tool with a Confirmation Step

**Track:** Banking | **Time box:** 25 min | **Pattern practiced:** understand → act (tool call) → **confirm** before executing

## Scenario
A customer messages support: "My card was stolen, please block it right
now." Unlike H1 (which only *reads* information), this agent must *take an
action that changes account state* — blocking a card. That means it needs a
safety step our read-only agent didn't: **explicit customer confirmation
before the irreversible action fires.**

## Your task
Build an agent loop with one tool, `block_card(card_last4: str, reason: str)`,
that:
1. Understands the customer's intent from free text.
2. Instead of calling `block_card` immediately, first **asks the customer to
   confirm** which card (if ambiguous) and that they want to proceed —
   i.e., the model's first turn should be a clarifying/confirmation
   question, not a tool call.
3. Only calls the `block_card` tool once the customer has explicitly
   confirmed (e.g., replies "yes, block it").
4. After the tool "executes" (stubbed — just prints and returns a fake
   confirmation number), the agent tells the customer it's done and what
   happens next (replacement card timeline).

This is a **two-turn** conversation minimum: customer message → agent asks
to confirm → customer confirms → agent calls tool → agent confirms
completion.

## Why this matters
This is the **act** step of the agentic CX loop (Topic 03) combined with a
guardrail from Topic 06: irreversible or financially consequential actions
need a human-confirmed checkpoint before the agent is allowed to execute
them. Contrast this with H1, where "acting" only meant retrieving and
answering — nothing changed in the real world, so no confirmation gate was
needed.

## Files
- `starter.py` — scaffold with TODOs and a stub `block_card` function.
- `solution.py` — reference solution using Claude's tool-use API with a
  system prompt that enforces "never call block_card without prior explicit
  user confirmation in this conversation."

## A note on the tool's input schema
`block_card`'s arguments are defined once as a **Pydantic model**
(`BlockCardInput`), and `BLOCK_CARD_TOOL["input_schema"]` is generated
straight from it (`BlockCardInput.model_json_schema()`). The executing
function re-validates the model's tool call against that same schema before
touching anything — belt-and-suspenders, since the API already constrains
what the model can submit, but the executing code should never blindly
trust a dict it received over the wire either.

## Setup
```bash
pip install anthropic pydantic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a second tool, `list_cards(customer_id)`, so the agent can resolve
  "my card" to a specific card if the customer has more than one, instead of
  just asking the customer to state the last 4 digits.
- Add a hard-coded daily limit: if the customer has already blocked 2 cards
  today, force escalation to a human instead of letting the agent execute a
  3rd block (foreshadows H3 and Topic 05).

## Discussion
- What's the failure mode if we skip the confirmation step and let the model
  call `block_card` on the first turn? Try it (remove the guard from the
  system prompt) and see how often it still asks vs. just acts.
