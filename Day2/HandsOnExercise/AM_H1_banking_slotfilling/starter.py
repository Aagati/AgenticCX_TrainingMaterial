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
import os
import sys
import re
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

# Windows consoles default to cp1252 and crash when the model emits an arrow,
# em-dash or curly quote. Force UTF-8 so a print() cannot kill the lab.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = Anthropic()
MODEL = "claude-sonnet-5"

# Resolve data next to THIS file, so the lab runs from any working directory.
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DATA_DIR, "mock_transactions.json")) as f:
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
    found: bool = Field(description="True if the customers message contains a value for this specific slot")
    value: Optional[str] = Field(default=None, description="The raw value as stated, unvalidated")
    approximate: bool = Field(default=False, description="True if the customer HEDGED the value ('around 90', 'about ten bucks', 'ninety-ish') rather than stating it")
    


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
    v = raw_value.strip()
    if slot == "account_last4":
        if len(v) == 4 and v.isdigit():
            return True, v
        else:
            return False, "The account number must be exactly 4 digits."
    elif slot == "transaction_date":
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return True, v
        except ValueError:
            return False, "The date must be in YYYY-MM-DD format."
    elif slot == "amount":
        amount = v.replace(",", "")
        match = re.search(r"-?\d+(?:\.\d+)?", amount)
        if match is None:
            return False, "I couldn't read the entered amount as a number - please provide it in numerals, example: 45.00"
        try:
            amount = float(match.group())
            if amount > 0:
                return True, amount
            else:
                return False, "The amount must be a positive number."
        except ValueError:
            return False, "The amount must be a valid number."
    elif slot == "reason":
        if len(v) >= 5:
            return True, v
        else:
            return False, "The reason must be at least 5 characters long."
        


def find_matching_transactions(slots: dict):
    """
    TODO 3: Given slots with account_last4, transaction_date, and amount
    filled in, return the list of transactions from TRANSACTIONS that match
    on account_last4 and transaction_date (ignore amount here — amount is
    what the CUSTOMER claims, which may differ slightly from the ledger, so
    disambiguation is done on account+date only and then presented to the
    customer to confirm which one).
    """
    return [
        t for t in TRANSACTIONS if t["account_last4"] == slots["account_last4"] and t["date"] == slots["transaction_date"]
    ]



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
    tolerance = max(AMOUNT_TOLERANCE_FLOOR, claimed * AMOUNT_TOLERANCE_RATIO)
    return abs(claimed - ledger) <= tolerance


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
    gap = abs(claimed - ledger)
    if gap < 0.01:
        return None, False

    hedge = "around" if approximate else ""
    if amounts_agree(claimed, ledger):
        return f"You mentioned {hedge} ${claimed:.2f}, but the ledger shows ${ledger:.2f}. We'll file against the ledger amount.", False
    else:
        return f"You mentioned {hedge} ${claimed:.2f}, but the ledger shows ${ledger:.2f}. The difference is ${gap:.2f}, which is larger than expected. We'll file against the ledger amount, but this has been flagged for review.", True


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
    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system = (
            f"""Extract only the value for the slot '{slot}' from the customer's message, if present. 
            Set the approximate field to true when the customer hedges the value ('about', 'around', 'roughly', '-ish') instead of stating it exactly."""
        ),
        tools=[EXTRACT_SLOT_TOOL],
        tool_choice={"type": "tool", "name": "submit_extraction"},
        messages=[
            {"role": "user", "content": customer_message}
        ],
    )
    tool_call = next((block for block in response.content if block.type == "tool_use"))
    return SlotExtraction(**tool_call.input)


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
            ok, result = validate_slot(slot, extraction.value)
            if ok:
                slots[slot] = result
                hedged[slot] = extraction.approximate
                filled = True
            else:
                print(f"AGENT: {result}")
                attempts += 1
        if not filled:
            print("AGENT: Sorry, I couldn't get that information. Let me connect you to a specialist.")
            return

    claimed = slots.get("amount")
    hedged_amount = hedged.get("amount")
    matches = find_matching_transactions(slots)
    matches.sort(key=lambda t: abs(t["amount"] - claimed) if claimed is not None else float('inf'))

    needs_review = False
    if len(matches) == 0:
        chosen = {"merchant": "(not found in our records)", "amount": slots["amount"]}
    elif len(matches) == 1:
        chosen = matches[0]
    else:
        print("AGENT: I found multiple transactions that match your account and date:")
        for i, match in enumerate(matches, 1):
            gap = abs(match["amount"] - claimed)
            note = "" if gap < 0.01 else f"  ({'closest to' if amounts_agree(claimed, match['amount']) else 'differs from'} the ${claimed:.2f} you mentioned)"
            print(f"{i}. Amount: ${match['amount']:.2f}, Merchant: {match['merchant']} {note}")
        if not any(amounts_agree(claimed, m['amount']) for m in matches):
            print(f"AGENT: Heads up — none of these are close to the "
                  f"${claimed:.2f} you mentioned. If none look right, the "
                  f"date might be off and we can search another day.")
            needs_review = True
        choice = input("YOU: ").strip()
        try:
            chosen = matches[int(choice) - 1]
        except (ValueError, IndexError):
            print("AGENT: I didn't catch a valid choice — let me connect you with a specialist.")
            return

    line, mismatch = reconcile_amount(claimed, hedged_amount, chosen["amount"])
    if line:
        print(f"\nAGENT: {line}")
    needs_review = needs_review or mismatch

    print("\nAGENT: Here's what I have —")
    print(f"  Account ending {slots['account_last4']}, {slots['transaction_date']}, "
      f"${chosen['amount']:.2f} at {chosen['merchant']}")
    if abs(claimed - chosen["amount"]) >= 0.01:
        # Both numbers survive into the record. "Customer claimed ~$90, ledger
        # shows $89.99" is evidence; keeping only one of them destroys it.
        hedge = "~" if hedged_amount else ""
        print(f"  (you said {hedge}${claimed:.2f} — filing against the ${chosen['amount']:.2f} charge)")
    print(f"  Reason: {slots['reason']}")
    confirm = input("AGENT: Shall I file this dispute? (yes/no)\nYOU: ").strip().lower()
    if confirm.startswith("y"):
        print("AGENT: Dispute filed. You'll hear back within 5-7 business days.")
        if needs_review:
            # Not a block — the customer may be right and the ledger stale.
            # The gap is flagged for a human instead of being averaged away.
            print("AGENT: I've also flagged the amount difference for a specialist to double-check.")
    else:
        print("AGENT: No problem, I won't file it. Let me know if anything changes.")



if __name__ == "__main__":
    run_flow()
