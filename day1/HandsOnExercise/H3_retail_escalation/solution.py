"""
H3 — Retail Escalation with Full Context Handoff (REFERENCE SOLUTION)
"""

import sys
import json
from typing import Optional

# Windows console defaults to cp1252, which can't encode characters like
# the rupee sign the model may include in ticket text — force UTF-8 so
# printing a ticket never crashes on a legitimate model response.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pydantic import BaseModel, Field, ValidationError, field_validator
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

REFUND_AUTHORITY_LIMIT = 1500

ORDERS = {
    "ORD-4021": {"status": "billed", "delivered": False, "amount": 2400, "item": "Wireless Headphones"},
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
    """Typed shape for a handoff package. The whole point of 'context-
    preserving handoff' is that a human can act without re-asking the
    customer anything — a schema alone can't guarantee the CONTENT is
    real, but it can guarantee the SHAPE is complete, and the validator
    below catches the most common way this fails in practice: placeholder
    text standing in for real information."""
    summary: str = Field(description="2-3 sentence summary of the issue")
    customer_sentiment: str = Field(description="e.g. frustrated, calm, urgent")
    order_id: Optional[str] = Field(default=None, description="Order id if applicable")
    requested_action: str = Field(description="What the customer wants done")
    conversation_transcript: str = Field(description="Full transcript so far")

    @field_validator("summary", "customer_sentiment", "requested_action", "conversation_transcript")
    @classmethod
    def no_placeholders(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("field is empty — every handoff field must contain real content")
        if v.strip().upper() in {"TBD", "N/A", "UNKNOWN"}:
            raise ValueError(f"field contains a placeholder ('{v}') instead of real content")
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
    try:
        payload = EscalationPayload(**kwargs)
    except ValidationError as e:
        # A malformed or placeholder-filled handoff is worse than no
        # handoff — it looks complete to a human agent but isn't. Reject
        # it and let the model try again rather than creating a bad ticket.
        return {"error": f"escalation payload rejected: {e}"}

    print("\n=== ESCALATION TICKET CREATED ===")
    for k, v in payload.model_dump().items():
        print(f"{k}: {v}")
    print("==================================\n")
    return {"ticket_id": "TCK-77190", "status": "queued_for_human", "eta_minutes": 3}


TOOLS = [GET_ORDER_STATUS_TOOL, ESCALATE_TOOL]
TOOL_FUNCS = {"get_order_status": get_order_status, "escalate_to_human": escalate_to_human}


def run_conversation(messages: list, max_iterations: int = 5) -> list:
    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_use_blocks:
            text = next(b.text for b in response.content if b.type == "text")
            messages.append({"role": "assistant", "content": text})
            return messages

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in tool_use_blocks:
            func = TOOL_FUNCS[block.name]
            result = func(**block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    messages.append({"role": "assistant", "content": "[max iterations reached]"})
    return messages


if __name__ == "__main__":
    convo = [{
        "role": "user",
        "content": (
            "My order ORD-4021 was never delivered but I was charged 2400 "
            "rupees. This is ridiculous, I want a full refund right now."
        ),
    }]
    convo = run_conversation(convo)
    print("AGENT:", convo[-1]["content"])
    # Expected flow:
    #  1. Model calls get_order_status("ORD-4021") -> sees delivered=False, amount=2400
    #  2. 2400 > REFUND_AUTHORITY_LIMIT (1500) -> model calls escalate_to_human
    #     with a real summary, sentiment "frustrated", order_id, requested
    #     action "full refund of 2400 INR", and full transcript.
    #  3. EscalationPayload validates cleanly (no placeholders) -> ticket printed.
    #  4. Final assistant text reassures the customer a specialist has context.
