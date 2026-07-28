# AM · H1 — Banking: Slot-Filling Dispute Flow

**Track:** Banking | **Time box:** 40 min | **Pattern practiced:** intent → slot-filling → error repair → reconciliation → disambiguation → confirmation

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
| `amount` | "45.00" | must parse to a positive number; track whether it was hedged |
| `reason` | "never received the item" | free text, min 5 chars |

Requirements:
1. **Ask for missing slots one at a time** — never ask for two slots in the
   same question.
2. **Validate on the way in.** If the customer gives an unparseable amount
   ("about forty-five bucks-ish") or an invalid date, **repair the error**:
   explain what's wrong in plain language and re-ask for just that slot —
   don't restart the whole flow.
3. **Reconcile the amount.** Customers remember charges approximately —
   *"about ninety dollars"* against a ledger entry of `89.99`. Matching
   deliberately ignores the amount so a fuzzy number can't produce zero
   results, which means the customer's figure and the ledger's figure are
   free to disagree. **Say so before filing:** *"You mentioned around $90 —
   the charge I found is $89.99. I'll use the amount on the account."* Keep
   both numbers in the record, and when the gap is too large to wave through,
   flag it for a human rather than blocking the customer.
4. **Disambiguate.** If `account_last4` + `transaction_date` matches more
   than one transaction in `mock_transactions.json`, list the candidates
   (amount + merchant) and ask the customer to pick one instead of guessing.
   Rank them by closeness to the amount the customer gave — and if *none*
   are close, tell them, because the date is usually what's wrong.
5. **Confirm before submission.** Once all slots are filled and resolved to
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

## Try these (they exercise different branches)
| Input | What should happen |
|---|---|
| `4471` / `2026-07-10` / `45` | Two charges that day — **disambiguation**, amounts match exactly |
| `4471` / `2026-07-09` / `about 90` | One charge at `$89.99` — **reconciliation**: the agent names the 1¢ correction, then files |
| `4471` / `2026-07-10` / `about 90` | Candidates are `$45.00` and `$12.50`, neither near `$90` — the agent warns the **date** may be wrong and flags the filing for review |
| `4471` / `2026-07-10` / `forty-five-ish` | **Error repair** if the extractor can't turn it into a number |

## Discussion (bring back to the group)
- What's the UX cost of asking for all four slots in one message, even if
  the model *could* parse a compound answer like "4471, July 10th, $45,
  never got the item"? When would you want to allow that shortcut anyway?
- Where do you set the reconciliation tolerance? Too tight and every rounding
  difference becomes a scary "I couldn't verify this"; too loose and a $90
  vs $890 gap sails through. Should the threshold be a percentage, a flat
  amount, or should it scale with the customer's risk profile?
- The agent files against the *ledger's* amount when the two disagree.
  What would it take for the customer's number to be the one that wins —
  and who gets to make that call?
