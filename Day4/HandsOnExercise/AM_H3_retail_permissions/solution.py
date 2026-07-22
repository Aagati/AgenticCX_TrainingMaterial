"""
AM · H3 — Retail Per-User Permissions (REFERENCE SOLUTION)
"""

import json
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("entitlements.json") as f:
    ENTITLEMENTS = json.load(f)

MODIFY_ORDER_TOOL = {
    "name": "modify_order",
    "description": "Cancel an order or modify its item quantity.",
    "input_schema": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "action": {"type": "string", "enum": ["cancel", "modify_quantity"]},
        },
        "required": ["order_id", "action"],
    },
}


def check_permission(user_id: str, order_id: str, action: str):
    if user_id not in ENTITLEMENTS:
        return False, "unknown user"
    entitlements = ENTITLEMENTS[user_id]
    if order_id not in entitlements["owns_orders"]:
        return False, "user does not own this order"
    flag = entitlements["can_cancel"] if action == "cancel" else entitlements["can_modify_quantity"]
    if not flag:
        return False, f"user lacks permission for {action}"
    return True, "allowed"


def execute_modify_order(order_id: str, action: str) -> dict:
    return {"order_id": order_id, "action": action, "status": "completed"}


def modify_order_gated(user_id: str, order_id: str, action: str) -> dict:
    allowed, reason = check_permission(user_id, order_id, action)
    if not allowed:
        return {"error": reason}
    return execute_modify_order(order_id, action)


def run_turn(user_id: str, user_message: str) -> str:
    system = "You are a retail support agent. Use modify_order for cancellation or quantity-change requests."
    messages = [{"role": "user", "content": user_message}]
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        tools=[MODIFY_ORDER_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return next(b.text for b in response.content if b.type == "text")

    result = modify_order_gated(user_id, **tool_use.input)

    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        tools=[MODIFY_ORDER_TOOL], messages=messages,
    )
    return next(b.text for b in followup.content if b.type == "text")


if __name__ == "__main__":
    print("--- user_101 (owns ORD-500, can_cancel=True) ---")
    print("AGENT:", run_turn("user_101", "Please cancel order ORD-500."))

    print("\n--- user_202 (does not own ORD-500) ---")
    print("AGENT:", run_turn("user_202", "Please cancel order ORD-500."))

# Expected: user_101 -> modify_order_gated allows it, order cancelled.
# user_202 -> check_permission fails on ownership ("user does not own
# this order"), agent relays a clear refusal, no state changed.
