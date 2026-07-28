"""
AM · H1 — Banking Slot-Filling Dispute Flow (STARTER)

Design note: we track slot state in Python, not just in the model's head.
The model's job is to (a) extract a TYPED value for the slot we just asked
about, (b) nothing else — validation, disambiguation, and "what's next"
all stay in Python. This is the standard production pattern: it's
auditable and testable in a way that "just let the model track everything"
is not.

You are building four named behaviors. Most people build the first, third
and fourth and never notice the second is missing:

    ERROR REPAIR    - unparseable input, re-ask with the specific problem
    RECONCILIATION  - the customer's number and the ledger's number disagree;
                      say so out loud before filing against the ledger's
    DISAMBIGUATION  - several candidates, ask instead of guessing
    CONFIRMATION    - explicit yes before anything is written

Try it afterwards with 4471 / 2026-07-09 / "about 90". There is one charge
that day, for $89.99. An agent without reconciliation files it silently and
the customer never learns the number changed.
"""

import json
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("mock_transactions.json") as f:
    TRANSACTIONS = json.load(f)

REQUIRED_SLOTS = ["account_last4", "transaction_date", "amount", "reason"]

SLOT_PROMPTS = {
    "account_last4": "Which account is this on? Just the last 4 digits is fine.",
    "transaction_date": "What date did the transaction happen? (e.g. 2026-07-10)",
    "amount": "What was the amount of the charge?",
    "reason": "In a few words, why are you disputing this charge?",
}


class SlotExtraction(BaseModel):
    """
    TODO 1: Define three fields:
      - found: bool — True if the customer's message contains a value for
        this specific slot
      - value: Optional[str] = None — the raw value as stated, unvalidated
      - approximate: bool = False — True if the customer HEDGED the value
        ("around 90", "about ten bucks", "ninety-ish") rather than stating
        it exactly
    Give each a Field(description=...).

    That third field is easy to skip and it's the one that matters later.
    validate_slot() normalizes "around ninety" to 90.0, so by the time the
    value reaches your flow the hedge is gone and a guess is indistinguishable
    from a precise figure. You need to know which it was before you can tell a
    customer "you said around $90, the charge is $89.99" — see TODO 4b.
    """
    pass


EXTRACT_SLOT_TOOL = {
    "name": "submit_extraction",
    "description": "Submit the extracted slot value, if present in the message.",
    "input_schema": SlotExtraction.model_json_schema(),
}


def validate_slot(slot: str, raw_value: str):
    """
    TODO 2: Validate and normalize `raw_value` for the given slot.
    Return (True, normalized_value) on success, or (False, error_message) on
    failure. Rules:
      - account_last4: must be exactly 4 digits -> return as string
      - transaction_date: must parse as YYYY-MM-DD -> return normalized string
      - amount: must parse as a positive float -> return as float
      - reason: must be at least 5 characters (after stripping) -> return as string
    """
    raise NotImplementedError


def find_matching_transactions(slots: dict):
    """
    TODO 3: Given slots with account_last4, transaction_date, and amount
    filled in, return the list of transactions from TRANSACTIONS that match
    on account_last4 and transaction_date (ignore amount here — amount is
    what the CUSTOMER claims, which may differ slightly from the ledger, so
    disambiguation is done on account+date only and then presented to the
    customer to confirm which one).
    """
    raise NotImplementedError


AMOUNT_TOLERANCE_RATIO = 0.10   # within 10% reads as ordinary mis-remembering
AMOUNT_TOLERANCE_FLOOR = 2.00   # ...but always allow at least $2 of slack


def amounts_agree(claimed: float, ledger: float) -> bool:
    """
    TODO 4a: Return True if `claimed` is within tolerance of `ledger`, using
    max(AMOUNT_TOLERANCE_FLOOR, claimed * AMOUNT_TOLERANCE_RATIO) as the
    allowed gap.

    $90 vs $89.99 is rounding. $90 vs $890 is a different transaction, a typo,
    or fraud. Those need different handling, so this returns a verdict the
    caller acts on rather than hiding a magic number inside an if-statement.
    """
    raise NotImplementedError


def reconcile_amount(claimed: float, approximate: bool, ledger: float):
    """
    TODO 4b — RECONCILIATION. Return a tuple (line_to_say, needs_review):
      - if the two amounts match to the cent: (None, False) — nothing to
        reconcile, and saying so would just be noise
      - if they differ but amounts_agree(): a line naming both numbers and
        stating you'll use the ledger amount, and needs_review=False
      - if they differ by more than tolerance: a line naming both numbers and
        the size of the gap, and needs_review=True

    Use `approximate` to phrase it honestly — "you mentioned around $90" reads
    very differently from "you mentioned $90" when you're about to file
    against $89.99.

    WHY THIS STEP EXISTS: find_matching_transactions() ignores the amount on
    purpose (TODO 3), which means the customer's number and the ledger's
    number are allowed to disagree and the flow will carry on regardless.
    Something has to NOTICE and say it out loud. Without this, the customer
    says "about $90", your summary prints "$89.99", and they're expected to
    catch a changed number in a summary line. Silent correction is how someone
    confirms a dispute on a transaction they never meant to dispute.

    needs_review must NOT block the dispute. The customer may be right and the
    ledger stale. Flag it for a human — that's the honest response to "I can't
    tell which of these two numbers is correct."
    """
    raise NotImplementedError


def extract_slot_value(slot: str, customer_message: str) -> SlotExtraction:
    """
    TODO 5: Call client.messages.create with tools=[EXTRACT_SLOT_TOOL] and
    tool_choice={"type": "tool", "name": "submit_extraction"} — this FORCES
    a structured response. System prompt: "Extract only the value for the
    slot '{slot}' from the customer's message, if present." Extract the
    tool_use block and return SlotExtraction(**tool_call.input).

    Tell the model when to set approximate=true, or it never will — add a
    sentence like: "Set approximate=true when the customer hedges the value
    ('about', 'around', 'roughly', '-ish') instead of stating it exactly."
    A field the prompt never mentions just sits at its default.
    """
    raise NotImplementedError


def run_flow():
    print("AGENT: I can help you dispute a transaction. Let's start.")
    slots = {}
    hedged = {}  # slot -> was the customer hedging? needed for TODO 7

    for slot in REQUIRED_SLOTS:
        filled = False
        attempts = 0
        while not filled and attempts < 3:
            print(f"AGENT: {SLOT_PROMPTS[slot]}")
            customer_message = input("YOU: ")
            extraction = extract_slot_value(slot, customer_message)
            if not extraction.found or extraction.value is None:
                print("AGENT: Sorry, I didn't catch that — could you try again?")
                attempts += 1
                continue

            # TODO 6: Call validate_slot(). If valid, store the normalized
            # value in slots[slot], record hedged[slot] = extraction.approximate,
            # and set filled=True. If invalid, print the error message returned
            # by validate_slot() and loop (this is the "error repair" behavior).
            #
            # Don't drop the hedge here — validate_slot() turns "around ninety"
            # into 90.0, so this line is the last place the uncertainty exists.
            raise NotImplementedError

    # TODO 7: Once all slots are filled, call find_matching_transactions().
    #
    # a) RANK, don't filter. Sort the matches by how close each one is to
    #    slots["amount"]. The claimed amount is too unreliable to exclude
    #    candidates with, but it's a good way to put the likeliest one first.
    #
    # b) DISAMBIGUATION. If more than one match, list them (amount + merchant)
    #    and ask the customer to pick one. If none of them are within
    #    amounts_agree() of the claimed amount, say so — when nothing on that
    #    date is close, the DATE is usually what's wrong, and telling them
    #    beats letting them pick a transaction they don't recognize.
    #
    # c) RECONCILIATION. Before the summary, call reconcile_amount() with the
    #    claimed amount, hedged["amount"], and the chosen transaction's amount.
    #    Print the line it returns. This has to come BEFORE the confirmation,
    #    not inside it — you are about to file a different number than the one
    #    the customer gave you, and that swap gets named out loud.
    #
    # d) CONFIRMATION. Print a summary and ask for explicit yes/no before
    #    "filing" (just print "Dispute filed." — no real backend). Keep BOTH
    #    numbers visible in the summary when they differ: "customer claimed
    #    ~$90, ledger shows $89.99" is evidence, and keeping only one of them
    #    destroys it.
    #
    #    If reconcile_amount() returned needs_review=True, file anyway but say
    #    it's been flagged for a specialist. Never block on the mismatch.
    raise NotImplementedError


if __name__ == "__main__":
    run_flow()
