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
    card_last4: str = Field(description="The last 4 digits of the card to block.")
    reason: str = Field(description="The reason for blocking the card.")


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
#  - tells it a vague/hesitant reply ("maybe", "I think so") does NOT count
#    as confirmation -- it should ask again rather than guess
SYSTEM_PROMPT = f""""
                    You are a banking support agent. You have access to the following tool:
                    {BLOCK_CARD_TOOL}
                    RULES TO FOLLOW FOR USING BLOCK_CARD TOOL:
                    1. You must NOT call the block_card tool unless the customer has given clear and explicit confirmation to block the card.
                    2. If the customer has not given a clear confirmation, YOU MUST ask a clarifying or confirming question before proceeding.
                    3.A vague or hesitant reply does NOT count towards confirmation, so make sure the rules are followed correctly.
                    4. If the user says NO or expresses that they dont want to proceed, you must terminate the conversation and not call the block_card tool.
                    5. After a card is blocked reassure the user that they will receive a new card in the mail within 5-7 business days and that they should contact support if they have any further queries.
                    6. Be precise and reassuring in your tone."""


def block_card(card_last4: str, reason: str) -> dict:
    """
    TODO 3: Validate the incoming arguments against BlockCardInput inside a
    try/except ValidationError (return {"error": ...} on failure — don't
    let a malformed call silently proceed). If valid, print a [SYSTEM]
    line and return {"status": "blocked", "confirmation_number": "BLK-88213",
    "card_last4": <validated value>}.
    """
    try:
        validate_input = BlockCardInput(card_last4=card_last4, reason=reason)
        print
    except ValidationError as e:
        return {"error": str(e)}
    print(f"[SYSTEM] Card ending {validate_input.card_last4} has been blocked for reason: {validate_input.reason}.")
    return {
        "status": "blocked",
        "confirmation_number": "BLOCKCARD_12345",
        "card_last4": validate_input.card_last4
    }
    


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
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=[BLOCK_CARD_TOOL],
        messages=messages
    )
    tool_call = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_call:
        tool_input = tool_call.input
        result = block_card(**tool_input)
        messages.append({"role": "tool_result", "content": result})
        follow_up_response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            tools=[BLOCK_CARD_TOOL],
            messages=messages
        )
        messages.append({"role": "assistant", "content": follow_up_response.content[0].text})
    else:
        messages.append({"role": "assistant", "content": response.content[0].text})
    return messages


if __name__ == "__main__":
    customer_msg_1 = "Hi, my card was stolen, please block it right now."
    print("CUSTOMER:", customer_msg_1)
    convo = [{"role": "user", "content": customer_msg_1}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    # This reply is deliberately NOT a clear confirmation -- watch whether your
    # system prompt makes the agent ask again instead of calling block_card here.
    customer_msg_2 = "Umm... I think so? I'm not totally sure it's the right move."
    print("\nCUSTOMER:", customer_msg_2)
    convo.append({"role": "user", "content": customer_msg_2})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    customer_msg_3 = "Yes, I'm sure. It's the one ending 4471, please block it."
    print("\nCUSTOMER:", customer_msg_3)
    convo.append({"role": "user", "content": customer_msg_3})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])
