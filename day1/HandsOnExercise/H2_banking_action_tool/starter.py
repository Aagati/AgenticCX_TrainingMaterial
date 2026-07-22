"""
H2 — Banking Action Tool with Confirmation Step (STARTER)
"""

from typing import Optional
from pydantic import BaseModel, Field, ValidationError
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"


class BlockCardInput(BaseModel):
    """
    TODO 1: Define the typed shape of block_card's arguments:
      - card_last4: str
      - reason: str
    Give each a Field(description=...).
    """
    pass


BLOCK_CARD_TOOL = {
    "name": "block_card",
    "description": (
        "Permanently blocks a debit/credit card so it can no longer be used. "
        "This is IRREVERSIBLE and must only be called after the customer has "
        "explicitly confirmed they want to proceed, in this conversation."
    ),
    "input_schema": BlockCardInput.model_json_schema(),
}

# TODO 2: Write a system prompt that:
#  - tells the model it's a banking support agent
#  - gives it the block_card tool for card-blocking requests
#  - explicitly forbids calling block_card unless the customer has already
#    given clear, explicit confirmation earlier in the conversation
#  - tells it to ask a clarifying/confirmation question first if it hasn't
#    been given one yet
SYSTEM_PROMPT = None  # TODO


def block_card(card_last4: str, reason: str) -> dict:
    """
    TODO 3: Validate the incoming arguments against BlockCardInput inside a
    try/except ValidationError (return {"error": ...} on failure — don't
    let a malformed call silently proceed). If valid, print a [SYSTEM]
    line and return {"status": "blocked", "confirmation_number": "BLK-88213",
    "card_last4": <validated value>}.
    """
    raise NotImplementedError


def run_turn(messages: list) -> list:
    """
    TODO 4: Call client.messages.create with tools=[BLOCK_CARD_TOOL] and the
    running `messages` list. If the response contains a tool_use block,
    execute block_card(**tool_input) via the function above, append a
    tool_result message, and make ONE follow-up call so the model can
    summarize the outcome to the customer. Return the updated messages list
    with the assistant's final text reply appended.

    If there's no tool_use block, just append the assistant's text reply.
    """
    raise NotImplementedError


if __name__ == "__main__":
    convo = [{"role": "user", "content": "Hi, my card was stolen, please block it right now."}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    convo.append({"role": "user", "content": "Yes, it's the one ending 4471, please block it."})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])
