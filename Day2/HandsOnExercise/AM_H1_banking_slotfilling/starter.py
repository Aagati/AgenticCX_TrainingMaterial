"""
AM · H1 — Banking Slot-Filling Dispute Flow (STARTER)

Design note: we track slot state in Python, not just in the model's head.
The model's job is to (a) extract a TYPED value for the slot we just asked
about, (b) nothing else — validation, disambiguation, and "what's next"
all stay in Python. This is the standard production pattern: it's
auditable and testable in a way that "just let the model track everything"
is not.
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
    TODO 1: Define two fields:
      - found: bool — True if the customer's message contains a value for
        this specific slot
      - value: Optional[str] = None — the raw value as stated, unvalidated
    Give each a Field(description=...).
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


def extract_slot_value(slot: str, customer_message: str) -> SlotExtraction:
    """
    TODO 4: Call client.messages.create with tools=[EXTRACT_SLOT_TOOL] and
    tool_choice={"type": "tool", "name": "submit_extraction"} — this FORCES
    a structured response. System prompt: "Extract only the value for the
    slot '{slot}' from the customer's message, if present." Extract the
    tool_use block and return SlotExtraction(**tool_call.input).
    """
    raise NotImplementedError


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

            # TODO 5: Call validate_slot(). If valid, store the normalized
            # value in slots[slot] and set filled=True. If invalid, print
            # the error message returned by validate_slot() and loop
            # (this is the "error repair" behavior).
            raise NotImplementedError

    # TODO 6: Once all slots are filled, call find_matching_transactions().
    # If more than one match, list them (amount + merchant) and ask the
    # customer to pick one (disambiguation) before continuing.
    # If exactly one match (or none), proceed directly.
    # Finally, print a summary and ask for explicit confirmation before
    # "filing" the dispute (just print "Dispute filed." — no real backend).
    raise NotImplementedError


if __name__ == "__main__":
    run_flow()
