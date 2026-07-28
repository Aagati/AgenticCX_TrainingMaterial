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
    3b. reconcile_amount     -> what to say when the customer and the ledger disagree
    4. extract_slot_value    -> the one narrow model call
    5. run_flow              -> the state machine that drives it all

Four named behaviors come out of this, and only the first three are the ones
people usually build:

    ERROR REPAIR    - unparseable input, re-ask with the specific problem
    DISAMBIGUATION  - several candidates, ask instead of guessing
    RECONCILIATION  - customer's number and the ledger's number disagree; say
                      so out loud before filing against the ledger's
    CONFIRMATION    - explicit yes before anything is written
"""

import json
import os
import re
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
    # Without this field, "around ninety dollars" and "ninety dollars" are
    # indistinguishable by the time they reach Python — the hedge is flattened
    # into 90.0 and the agent treats a guess as exact. Capturing HOW SURE the
    # customer was is what lets reconcile_amount() phrase the mismatch
    # honestly instead of silently overwriting their number.
    approximate: bool = Field(
        default=False,
        description="True if the customer hedged the value ('around 90', 'about ten bucks', "
                    "'ninety-ish', 'roughly') rather than stating it exactly",
    )


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
        # The extractor returns the value AS THE CUSTOMER STATED IT, so this
        # routinely receives "about 90 dollars" or "$1,234.50" rather than a
        # bare number. float() on any of those raises, which would send a
        # perfectly understandable answer back through error repair.
        #
        # So: pull out the first number and use it. The line this draws is
        # "are there digits?" — "about 90 dollars" is readable, "ninety-ish"
        # genuinely is not and still gets repaired. Note we deliberately do
        # NOT try to interpret number words; guessing at "ninety-ish" is how
        # you file a dispute for an amount the customer never said.
        cleaned = v.replace(",", "")
        # The leading -? matters: without it "-5" parses as 5.0 and sails past
        # the positive-number check below.
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match is None:
            return False, "I couldn't read that as an amount — could you give me just the number, like 45.00?"
        amount = float(match.group())
        if amount <= 0:
            return False, "The amount needs to be a positive number — what was the charge?"
        return True, amount

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


# ---------- 3b. Reconciliation ----------
#
# find_matching_transactions() deliberately ignores the amount, which means the
# customer's number and the ledger's number can disagree and the flow will
# happily carry on. Something has to NOTICE that and say it out loud.
#
# Without this step the correction is silent: the customer says "about $90",
# the summary prints "$89.99", and they're expected to spot a changed number
# in a summary line. Silent correction is how a customer confirms a dispute on
# a transaction they never meant.

AMOUNT_TOLERANCE_RATIO = 0.10   # within 10% reads as ordinary mis-remembering
AMOUNT_TOLERANCE_FLOOR = 2.00   # ...but always allow at least $2 of slack


def amounts_agree(claimed: float, ledger: float) -> bool:
    """Is the gap small enough to be normal human recall, or is it a red flag?

    The threshold is a policy decision, so it lives in named constants rather
    than a magic number buried in an if. $90 vs $89.99 is rounding. $90 vs
    $890 is a different transaction, a typo, or fraud — and the three need
    different handling, which is why this returns a verdict the caller acts on.
    """
    tolerance = max(AMOUNT_TOLERANCE_FLOOR, claimed * AMOUNT_TOLERANCE_RATIO)
    return abs(claimed - ledger) <= tolerance


def reconcile_amount(claimed: float, approximate: bool, ledger: float):
    """Returns (line_to_say, needs_review).

    line_to_say is None when the two amounts match to the cent — there is
    nothing to reconcile and saying so would just be noise.

    needs_review is True when the gap is too big to wave through. Note it does
    NOT block the dispute: the customer may be right and the ledger stale. It
    marks the record for a human, which is the honest response to "I can't
    tell which of these numbers is correct."
    """
    gap = abs(claimed - ledger)
    if gap < 0.01:
        return None, False

    hedge = "around " if approximate else ""
    if amounts_agree(claimed, ledger):
        return (f"You mentioned {hedge}${claimed:.2f} — the charge I found is "
                f"${ledger:.2f}. I'll use the amount on the account."), False
    return (f"You mentioned {hedge}${claimed:.2f}, but the closest charge I can see is "
            f"${ledger:.2f} — that's a ${gap:.2f} difference, so I want to check "
            f"before filing anything."), True


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
        system=(
            f"Extract only the value for the slot '{slot}' from the customer's message, "
            "if present. Set approximate=true when the customer hedges the value "
            "('about', 'around', 'roughly', '-ish') instead of stating it exactly."
        ),
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
    slots = {}       # the conversation state — one source of truth
    hedged = {}      # slot -> was the customer hedging? kept for reconciliation

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
                # Carry the hedge forward. validate_slot() normalizes "about
                # ninety" to 90.0 and the uncertainty would be lost right here
                # if we didn't record it alongside the value.
                hedged[slot] = extraction.approximate
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
    claimed_amount = slots["amount"]
    amount_hedged = hedged.get("amount", False)

    matches = find_matching_transactions(slots)
    # The claimed amount is useless for FILTERING (it's half-remembered) but
    # excellent for RANKING. Sorting by proximity puts the most likely
    # candidate first without ever excluding the others.
    matches.sort(key=lambda t: abs(t["amount"] - claimed_amount))

    needs_review = False
    if len(matches) > 1:
        print("AGENT: I found more than one transaction on that date. Which one is it?")
        for i, t in enumerate(matches, 1):
            # Show each candidate's distance from what the customer said, so a
            # list of numbers becomes a list of numbers they can reason about.
            gap = abs(t["amount"] - claimed_amount)
            note = "" if gap < 0.01 else f"  ({'closest to' if amounts_agree(claimed_amount, t['amount']) else 'differs from'} the ${claimed_amount:.2f} you mentioned)"
            print(f"  {i}. ${t['amount']:.2f} at {t['merchant']}{note}")
        if not amounts_agree(claimed_amount, matches[0]["amount"]):
            # Nothing on this date is close to what they remember. Usually the
            # DATE is wrong, not the amount — say so rather than letting them
            # pick a transaction they don't recognize.
            print(f"AGENT: Heads up — none of these are close to the "
                  f"${claimed_amount:.2f} you mentioned. If none look right, the "
                  f"date might be off and we can search another day.")
            needs_review = True
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

    # RECONCILIATION: say the correction out loud BEFORE the summary. The
    # customer stated one number and we're about to file a different one —
    # that swap gets named, not slipped into a summary line and hoped past.
    line, mismatch = reconcile_amount(claimed_amount, amount_hedged, chosen["amount"])
    if line:
        print(f"\nAGENT: {line}")
    needs_review = needs_review or mismatch

    # CONFIRMATION GATE: read the collected state back and require an explicit
    # yes before the write. This is the same principle as Day 1's H2 lab —
    # anything with real-world consequences gets confirmed first, and the
    # confirmation is enforced by an if-statement, not by asking the model to
    # please remember to check.
    print("\nAGENT: Here's what I have —")
    print(f"  Account ending {slots['account_last4']}, {slots['transaction_date']}, "
          f"${chosen['amount']:.2f} at {chosen['merchant']}")
    if abs(claimed_amount - chosen["amount"]) >= 0.01:
        # Both numbers survive into the record. "Customer claimed ~$90, ledger
        # shows $89.99" is evidence; keeping only one of them destroys it.
        hedge = "~" if amount_hedged else ""
        print(f"  (you said {hedge}${claimed_amount:.2f} — filing against the ${chosen['amount']:.2f} charge)")
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

# Try it with:
#   4471 / 2026-07-10 / 45      -> two matches, exact amount: disambiguation only
#   4471 / 2026-07-09 / "about 90"
#                               -> RECONCILIATION: one match at $89.99, gap is
#                                  1 cent, agent names the correction and files
#   4471 / 2026-07-10 / "about 90"
#                               -> RECONCILIATION under ambiguity: candidates are
#                                  $45.00 and $12.50, neither close to $90, so the
#                                  agent warns the DATE may be wrong and flags the
#                                  filing for review
#   4471 / 2026-07-10 / "forty-five-ish"
#                               -> ERROR REPAIR if the model can't normalize it to
#                                  a number, then a clean retry
