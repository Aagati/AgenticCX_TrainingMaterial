# AM · H1 — Banking: Slot-Filling Dispute Flow

**Track:** Banking | **Time box:** 40 min | **Pattern practiced:** intent → slot-filling → disambiguation → error repair → confirmation

## Scenario
A customer wants to dispute a transaction: *"I want to dispute a charge."* Before
anything can happen, you need four pieces of information — which account,
which transaction, the amount, and the reason. A good conversation designer
never asks for all four in a wall of text, and never loses track of what's
already been answered.

## Your task
Build a multi-turn agent that fills these **slots** one at a time:

| Slot | Example | Notes |
|---|---|---|
| `account_last4` | "4471" | 4 digits |
| `transaction_date` | "2026-07-10" | must parse to a real date |
| `amount` | "45.00" | must parse to a positive number |
| `reason` | "never received the item" | free text, min 5 chars |

Requirements:
1. **Ask for missing slots one at a time** — never ask for two slots in the
   same question.
2. **Validate on the way in.** If the customer gives an unparseable amount
   ("about forty-five bucks-ish") or an invalid date, **repair the error**:
   explain what's wrong in plain language and re-ask for just that slot —
   don't restart the whole flow.
3. **Disambiguate.** If `account_last4` + `transaction_date` matches more
   than one transaction in `mock_transactions.json`, list the candidates
   (amount + merchant) and ask the customer to pick one instead of guessing.
4. **Confirm before submission.** Once all slots are filled and resolved to
   a single transaction, summarize it back and ask for explicit confirmation
   before "filing" the dispute (a stubbed function is fine).

## Why this matters
This is today's Topic 01 (conversation design) made concrete: intents,
slot-filling, disambiguation, and error repair are the four skills every
production conversational agent needs, and they're mostly **conversation
design decisions**, not model capability — the same underlying model
produces a much worse experience if the flow doesn't track state properly.

## Files
- `mock_transactions.json` — a small transaction ledger to query against.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic pydantic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Handle the customer changing their mind mid-flow ("actually, make that the
  transaction on the 9th, not the 10th") without losing the other slots
  already filled.
- Cap error repair at 2 retries per slot, then offer to escalate to a human
  instead of looping forever.

## Discussion (bring back to the group)
- What's the UX cost of asking for all four slots in one message, even if
  the model *could* parse a compound answer like "4471, July 10th, $45,
  never got the item"? When would you want to allow that shortcut anyway?
