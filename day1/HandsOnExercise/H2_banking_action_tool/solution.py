"""
H2 — Banking Action Tool with Confirmation Step (REFERENCE SOLUTION)
"""

from typing import Optional
from pydantic import BaseModel, Field, ValidationError
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"


class BlockCardInput(BaseModel):
    """Typed shape for the block_card tool's arguments. Even though the
    Anthropic API already validates against BLOCK_CARD_TOOL's JSON schema
    before the model can call it, re-validating on the executing side with
    Pydantic is cheap insurance — the two schemas are maintained in one
    place conceptually, but a mismatch or a future manual tool_use
    construction bypassing the API would still get caught here."""
    card_last4: str = Field(description="Last 4 digits of the card")
    reason: str = Field(description="Why the card is being blocked")


BLOCK_CARD_TOOL = {
    "name": "block_card",
    "description": (
        "Permanently blocks a debit/credit card so it can no longer be used. "
        "This is IRREVERSIBLE and must only be called after the customer has "
        "explicitly confirmed they want to proceed, in this conversation."
    ),
    "input_schema": BlockCardInput.model_json_schema(),
}

SYSTEM_PROMPT = """You are a banking support agent. You have access to a
block_card tool that PERMANENTLY and IRREVERSIBLY blocks a card.

Rules:
1. Never call block_card on the first mention of a lost/stolen card. First,
   confirm with the customer: (a) which card, if not already clear from
   context (ask for last 4 digits if multiple cards are possible), and
   (b) that they explicitly want you to proceed with blocking it now.
2. Only call block_card after the customer has given clear, explicit
   confirmation ("yes", "please block it", "go ahead", etc.) in a message
   that came AFTER your confirmation question.
3. If the customer's reply is vague, hesitant, or uncertain ("maybe", "I
   think so", "not sure", etc.), that is NOT confirmation — ask them to
   confirm clearly before proceeding, don't guess at their intent.
4. After the tool executes, tell the customer it's done, give them the
   confirmation number, and mention a replacement card typically arrives in
   5-7 business days.
5. Be concise and reassuring — the customer is likely stressed about fraud."""


def block_card(card_last4: str, reason: str) -> dict:
    """Validate the tool's own input before touching anything, then execute."""
    try:
        validated = BlockCardInput(card_last4=card_last4, reason=reason)
    except ValidationError as e:
        return {"error": f"invalid tool input: {e}"}
    print(f"[SYSTEM] Blocking card ending {validated.card_last4}. Reason: {validated.reason}")
    return {"status": "blocked", "confirmation_number": "BLK-88213", "card_last4": validated.card_last4}


def run_turn(messages: list) -> list:
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        tools=[BLOCK_CARD_TOOL],
        messages=messages,
    )

    tool_use_block = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use_block is None:
        text = next(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": text})
        return messages

    result = block_card(**tool_use_block.input)

    messages.append({"role": "assistant", "content": response.content})
    messages.append({
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": tool_use_block.id,
            "content": str(result),
        }],
    })

    followup = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=[BLOCK_CARD_TOOL],
        messages=messages,
    )
    final_text = next(b.text for b in followup.content if b.type == "text")
    messages.append({"role": "assistant", "content": final_text})
    return messages


if __name__ == "__main__":
    customer_msg_1 = "Hi, my card was stolen, please block it right now."
    print("CUSTOMER:", customer_msg_1)
    convo = [{"role": "user", "content": customer_msg_1}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])
    # Expected: agent asks which card / for confirmation, does NOT call the tool yet.

    customer_msg_2 = "Umm... I think so? I'm not totally sure it's the right move."
    print("\nCUSTOMER:", customer_msg_2)
    convo.append({"role": "user", "content": customer_msg_2})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])
    # Expected: this is NOT clear confirmation -- the agent should ask again,
    # not call block_card. If [SYSTEM] Blocking... prints here, the guardrail failed.

    customer_msg_3 = "Yes, I'm sure. It's the one ending 4471, please block it."
    print("\nCUSTOMER:", customer_msg_3)
    convo.append({"role": "user", "content": customer_msg_3})
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])
    # Expected: [SYSTEM] Blocking card ending 4471... printed, then agent
    # confirms completion with confirmation number + replacement timeline.
