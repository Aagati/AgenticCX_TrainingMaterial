"""
H3 — Retail Escalation with Full Context Handoff (STARTER)
"""

import json
from typing import Optional
from pydantic import BaseModel, Field, ValidationError, field_validator
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

REFUND_AUTHORITY_LIMIT = 1500

ORDERS = {
    "ORD-4021": {"status": "billed", "delivered": False, "amount": 2400, "item": "Wireless Headphones"},
    "ORD-3015": {"status": "billed", "delivered": False, "amount": 900, "item": "Bluetooth Speaker"},
}

GET_ORDER_STATUS_TOOL = {
    "name": "get_order_status",
    "description": "Look up the delivery/billing status of an order by id.",
    "input_schema": {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
    },
}


class EscalationPayload(BaseModel):
    """
    TODO 1: Define the typed shape of a handoff package:
      - summary: str
      - customer_sentiment: str
      - order_id: Optional[str] = None
      - requested_action: str
      - conversation_transcript: str
    Give each a Field(description=...).

    TODO 2: Add a @field_validator on summary, customer_sentiment,
    requested_action, and conversation_transcript that rejects empty
    strings AND common placeholder values ("TBD", "N/A", "UNKNOWN",
    case-insensitive) — raise ValueError with a clear message.
    """
    summary: str = Field(description="A concise summary of the customer's issue.")
    customer_sentiment: str = Field(description="The customer's emotional state (e.g., frustrated, confused, angry).")
    order_id: Optional[str] = Field(default=None, description="The order ID relevant to the issue, if applicable.")
    requested_action: str = Field(description="The specific action the customer is requesting (e.g., refund, replacement, cancellation).")
    conversation_transcript: str = Field(description="The full transcript of the conversation so far, including both customer and agent messages.") 

    @field_validator(
        "summary", "customer_sentiment", "requested_action", "conversation_transcript"
    )

    @classmethod
    def no_placeholder(cls, v):
        if not v or v.strip().upper() in {"TBD", "N/A", "UNKNOWN"}:
            raise ValueError("Field cannot be empty or a placeholder value (TBD, N/A, UNKNOWN).")
        return v
    


ESCALATE_TOOL = {
    "name": "escalate_to_human",
    "description": (
        "Hand off this conversation to a human support specialist. Use this "
        "when the request is outside your authority (e.g., refund amount "
        "exceeds the limit) or the customer explicitly asks for a human."
    ),
    "input_schema": EscalationPayload.model_json_schema(),
}

SYSTEM_PROMPT = f"""You are a retail support agent. You can look up order
status with get_order_status. You are NOT authorized to approve refunds
above {REFUND_AUTHORITY_LIMIT} INR under any circumstances.

Escalate to a human via escalate_to_human when EITHER is true:
- The customer's requested refund/resolution exceeds your authority limit.
- The customer explicitly asks for a human, supervisor, or manager.

Do not stall, apologize repeatedly, or pretend to process a refund you
cannot authorize. Look up the order first if relevant, then escalate
promptly once you determine it's needed.

When you escalate, fill in every field of escalate_to_human with specific,
concrete information from this conversation — no placeholders like "TBD".
The conversation_transcript field should contain the full exchange so far
so the human never has to ask the customer to repeat themselves.

After escalating, tell the customer in one or two warm sentences that
they're being connected to a specialist who already has full context on
their issue."""


def get_order_status(order_id: str) -> dict:
    return ORDERS.get(order_id, {"error": "order not found"})


def escalate_to_human(**kwargs) -> dict:
    """
    TODO 3: Construct EscalationPayload(**kwargs) inside a try/except
    ValidationError. On failure, return {"error": f"escalation payload
    rejected: {e}"} WITHOUT printing a ticket — a malformed handoff should
    never look like a successful one. On success, print the ticket details
    and return {"ticket_id": "TCK-77190", "status": "queued_for_human",
    "eta_minutes": 3}.
    """
    try:
        payload = EscalationPayload(**kwargs)
    except ValidationError as e:
        return {"error": f"escalation payload rejected: {e}"}
    
    print(f"[SYSTEM] Escalation ticket created with details: {payload.json()}")
    return {"ticket_id": "TCK-77190", "status": "queued_for_human", "eta_minutes": 3}



TOOLS = [GET_ORDER_STATUS_TOOL, ESCALATE_TOOL]
TOOL_FUNCS = {"get_order_status": get_order_status, "escalate_to_human": escalate_to_human}


def run_conversation(messages: list, max_iterations: int = 5) -> list:
    """
    TODO 4: Same multi-tool-call loop as before — call the model, execute
    ANY tool_use blocks in the response via TOOL_FUNCS, append tool_result
    messages, and loop until the model responds with plain text (or
    max_iterations is hit).
    """
    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            messages.append({"role": "assistant", "content": response.content[0].text})
            break

        for block in tool_use_blocks:
            tool_name = block.tool.name
            tool_input = block.input
            tool_func = TOOL_FUNCS.get(tool_name)
            if tool_func:
                result = tool_func(**tool_input)
                messages.append({"role": "tool_result", "content": json.dumps(result)})
    return messages


if __name__ == "__main__":
    print("=== Conversation 1: refund ABOVE authority limit -- should escalate ===")
    customer_msg_1 = (
        "My order ORD-4021 was never delivered but I was charged 2400 "
        "rupees. This is ridiculous, I want a full refund right now."
    )
    print("CUSTOMER:", customer_msg_1)
    convo = [{"role": "user", "content": customer_msg_1}]
    convo = run_conversation(convo)
    print("AGENT:", convo[-1]["content"])

    print("\n=== Conversation 2: refund WITHIN authority limit -- should NOT escalate ===")
    customer_msg_2 = (
        "My order ORD-3015 never showed up either and I was charged 900 "
        "rupees. Can I get a refund?"
    )
    print("CUSTOMER:", customer_msg_2)
    convo2 = [{"role": "user", "content": customer_msg_2}]
    convo2 = run_conversation(convo2)
    print("AGENT:", convo2[-1]["content"])
