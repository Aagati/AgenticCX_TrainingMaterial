"""
AM · H1 — Banking Slot-Filling Dispute Flow (REFERENCE SOLUTION)
"""

import json
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv() #Load environment variables

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("Day2\\HandsOnExercise\\AM_H1_banking_slotfilling\\mock_transactions.json") as f:
    TRANSACTIONS = json.load(f)

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
    "name": "submit_extraction",
    "description": "Submit the extracted slot value, if present in the message.",
    "input_schema": SlotExtraction.model_json_schema(),
}


def validate_slot(slot: str, raw_value: str):
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
    return [
        t for t in TRANSACTIONS
        if t["account_last4"] == slots["account_last4"] and t["date"] == slots["transaction_date"]
    ]


def extract_slot_value(slot: str, customer_message: str) -> SlotExtraction:
    """Narrow, single-purpose, TYPED extraction call — forced through a
    tool so the result is a validated SlotExtraction, not free text we'd
    otherwise have to parse for a magic sentinel value."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        system=f"Extract only the value for the slot '{slot}' from the customer's message, if present.",
        tools=[EXTRACT_SLOT_TOOL],
        tool_choice={"type": "tool", "name": "submit_extraction"},
        messages=[{"role": "user", "content": customer_message}],
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    return SlotExtraction(**tool_call.input)


def run_flow():
    print("AGENT: I can help you dispute a transaction. Let's start.")
    slots = {}

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

            ok, result = validate_slot(slot, extraction.value)
            if ok:
                slots[slot] = result
                filled = True
            else:
                print(f"AGENT: {result}")
                attempts += 1

        if not filled:
            print("AGENT: I'm having trouble getting that information — let me connect you with a specialist.")
            return

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
        chosen = {"merchant": "(not found in our records)", "amount": slots["amount"]}

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
