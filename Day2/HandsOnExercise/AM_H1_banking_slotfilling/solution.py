"""
AM · H1 — Banking Slot-Filling Dispute Flow (REFERENCE SOLUTION)

THE PATTERN: slot filling with the state machine in Python, not in the model.

The model does exactly one job here — extract a typed value for the ONE slot
we just asked about. Everything else (which slot comes next, whether a value
is valid, how many retries are left, whether to file) is ordinary Python.

Why it's built this way: a dispute flow is a regulated, auditable process. If
the model "tracks the conversation" you cannot unit-test the flow, you cannot
prove the confirmation step happened, and a single bad turn can skip a
required field. With the loop in Python, the flow is testable without calling
the API at all, and the model failing just means one more retry.

Read this file in the order the flow actually runs:
    1. slot definitions      -> what we must collect
    2. SlotExtraction        -> the typed contract the model must answer in
    3. validate_slot         -> Python decides what counts as valid
    4. extract_slot_value    -> the one narrow model call
    5. run_flow              -> the state machine that drives it all
"""

import json
import os
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()  # reads ANTHROPIC_API_KEY from .env

client = Anthropic()
MODEL = "claude-sonnet-5"

# Resolve data next to THIS file, so the lab runs from any working directory.
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DATA_DIR, "mock_transactions.json")) as f:
    TRANSACTIONS = json.load(f)

# ---------- 1. What we must collect ----------
#
# The slot list IS the flow. Order is deliberate and lives in Python: change
# this list and the conversation changes, with no prompt edits anywhere.
REQUIRED_SLOTS = ["account_last4", "transaction_date", "amount", "reason"]

SLOT_PROMPTS = {
    "account_last4": "Which account is this on? Just the last 4 digits is fine.",
    "transaction_date": "What date did the transaction happen? (e.g. 2026-07-10)",
    "amount": "What was the amount of the charge?",
    "reason": "In a few words, why are you disputing this charge?",
}


class SlotExtraction(BaseModel):
    """Typed extraction result. Using found: bool instead of a magic 'NONE'
    sentinel string means the state machine below never has to parse the
    model's free text to figure out whether it succeeded — the model has
    to commit to a structured answer, and Python decides what happens next."""
    found: bool = Field(description="True if the customer's message contains a value for this specific slot")
    value: Optional[str] = Field(default=None, description="The raw value as the customer stated it, unvalidated")


EXTRACT_SLOT_TOOL = {
    # Pydantic generates the JSON Schema, so the model's contract and the
    # class we parse into can never drift apart. Add a field to SlotExtraction
    # and the tool schema updates itself.
    "name": "submit_extraction",
    "description": "Submit the extracted slot value, if present in the message.",
    "input_schema": SlotExtraction.model_json_schema(),
}


# ---------- 3. Validation: Python decides, not the model ----------

def validate_slot(slot: str, raw_value: str):
    """Returns (True, normalized_value) or (False, message_to_show_customer).

    Note what this buys us: the error message a customer sees on bad input is
    written HERE, deterministically. It is not generated, so it cannot drift,
    cannot hallucinate a rule, and can be reviewed by compliance once.

    Also note it NORMALIZES, not just checks — "$1,234.50" comes back as the
    float 1234.50. Everything downstream gets clean typed data.
    """
    v = raw_value.strip()
    if slot == "account_last4":
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 4:
            return False, "That doesn't look like 4 digits — could you give me just the last 4 digits of the account?"
        return True, digits

    if slot == "transaction_date":
        try:
            parsed = datetime.strptime(v, "%Y-%m-%d")
            return True, parsed.strftime("%Y-%m-%d")
        except ValueError:
            return False, "I couldn't read that as a date — could you use the format YYYY-MM-DD, like 2026-07-10?"

    if slot == "amount":
        cleaned = v.replace("$", "").replace(",", "")
        try:
            amount = float(cleaned)
            if amount <= 0:
                return False, "The amount needs to be a positive number — what was the charge?"
            return True, amount
        except ValueError:
            return False, "I couldn't read that as an amount — could you give me just the number, like 45.00?"

    if slot == "reason":
        if len(v) < 5:
            return False, "Could you say a bit more about why you're disputing this charge?"
        return True, v

    return False, "Unrecognized slot."


def find_matching_transactions(slots: dict):
    # Matches on account + date ONLY, deliberately ignoring amount. The amount
    # is what the customer *remembers*; the ledger is what actually happened,
    # and those differ often (tip added, currency conversion, pending vs
    # settled). Filtering on a half-remembered number would silently return
    # zero matches. Instead we over-match and let the customer disambiguate.
    return [
        t for t in TRANSACTIONS
        if t["account_last4"] == slots["account_last4"] and t["date"] == slots["transaction_date"]
    ]


# ---------- 4. The one model call ----------

def extract_slot_value(slot: str, customer_message: str) -> SlotExtraction:
    """Narrow, single-purpose, TYPED extraction call.

    Three things make this reliable, and all three are worth copying:

    1. tool_choice={"type": "tool", ...} FORCES the model to call the tool.
       Without it the model may reply with chatty prose ("Sure, that looks
       like account 4471!") and there is nothing structured to parse.
    2. The system prompt names ONE slot. Asking for all four at once means a
       partial answer is ambiguous — you can't tell "not mentioned" apart
       from "model overlooked it".
    3. SlotExtraction(**tool_call.input) re-validates through Pydantic. The
       schema is a strong hint to the model, not a hard guarantee, so we
       still parse rather than trusting the payload shape.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=f"Extract only the value for the slot '{slot}' from the customer's message, if present.",
        tools=[EXTRACT_SLOT_TOOL],
        tool_choice={"type": "tool", "name": "submit_extraction"},
        messages=[{"role": "user", "content": customer_message}],
    )
    # Safe to use next() without a default here only because tool_choice
    # guarantees a tool_use block exists. Drop tool_choice and this line
    # becomes a StopIteration waiting to happen.
    tool_call = next(b for b in response.content if b.type == "tool_use")
    return SlotExtraction(**tool_call.input)


# ---------- 5. The state machine ----------

def run_flow():
    """The whole conversation policy, in plain Python.

    Nothing in this function is generated: which question comes next, when to
    give up, when to escalate, and when to file are all decisions you can read
    off the code and test without an API key.
    """
    print("AGENT: I can help you dispute a transaction. Let's start.")
    slots = {}  # the conversation state — one source of truth

    for slot in REQUIRED_SLOTS:
        filled = False
        attempts = 0
        # Bounded retries. An unbounded "keep asking until valid" loop is how
        # a stuck customer ends up trapped with a bot forever; 3 strikes then
        # a human. This ceiling is a CX decision, so it belongs in code.
        while not filled and attempts < 3:
            print(f"AGENT: {SLOT_PROMPTS[slot]}")
            customer_message = input("YOU: ")
            extraction = extract_slot_value(slot, customer_message)
            if not extraction.found or extraction.value is None:
                print("AGENT: Sorry, I didn't catch that — could you try again?")
                attempts += 1
                continue

            # ERROR REPAIR: on invalid input we re-prompt with the SPECIFIC
            # problem ("that isn't 4 digits") rather than repeating the
            # original question. Generic re-asking is what makes bots feel
            # broken — the customer can't tell what they did wrong.
            ok, result = validate_slot(slot, extraction.value)
            if ok:
                slots[slot] = result
                filled = True
            else:
                print(f"AGENT: {result}")
                attempts += 1

        if not filled:
            # ESCALATION: out of retries. Note we bail on the whole flow —
            # a half-filled dispute is worse than no dispute.
            print("AGENT: I'm having trouble getting that information — let me connect you with a specialist.")
            return

    # DISAMBIGUATION: the flow's second branch. Same account and date can hold
    # several charges, and picking one for the customer risks disputing the
    # wrong transaction. When ambiguous, ask — don't guess.
    matches = find_matching_transactions(slots)
    if len(matches) > 1:
        print("AGENT: I found more than one transaction on that date. Which one is it?")
        for i, t in enumerate(matches, 1):
            print(f"  {i}. ${t['amount']:.2f} at {t['merchant']}")
        choice = input("YOU: ").strip()
        try:
            chosen = matches[int(choice) - 1]
        except (ValueError, IndexError):
            print("AGENT: I didn't catch a valid choice — let me connect you with a specialist.")
            return
    elif len(matches) == 1:
        chosen = matches[0]
    else:
        # No ledger match. We still let the dispute proceed on the customer's
        # own numbers rather than dead-ending them — the customer may be right
        # and our mock data incomplete. Real systems flag this for review.
        chosen = {"merchant": "(not found in our records)", "amount": slots["amount"]}

    # CONFIRMATION GATE: read the collected state back and require an explicit
    # yes before the write. This is the same principle as Day 1's H2 lab —
    # anything with real-world consequences gets confirmed first, and the
    # confirmation is enforced by an if-statement, not by asking the model to
    # please remember to check.
    print("\nAGENT: Here's what I have —")
    print(f"  Account ending {slots['account_last4']}, {slots['transaction_date']}, "
          f"${chosen['amount']:.2f} at {chosen['merchant']}")
    print(f"  Reason: {slots['reason']}")
    confirm = input("AGENT: Shall I file this dispute? (yes/no)\nYOU: ").strip().lower()
    if confirm.startswith("y"):
        print("AGENT: Dispute filed. You'll hear back within 5-7 business days.")
    else:
        print("AGENT: No problem, I won't file it. Let me know if anything changes.")


if __name__ == "__main__":
    run_flow()

# Try it with: account 4471, date 2026-07-10 (two matches -> disambiguation),
# an invalid amount like "forty-five-ish" (error repair), then a valid one.
