"""
AM · H3 — Retail Per-User Permissions (STARTER)
"""

import json
from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

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
    """
    TODO 1: Look up ENTITLEMENTS[user_id] (return (False, "unknown user")
    if user_id isn't in ENTITLEMENTS). If order_id not in
    entitlements["owns_orders"], return (False, "user does not own this order").
    Otherwise check the action-specific flag:
      - action == "cancel" -> entitlements["can_cancel"]
      - action == "modify_quantity" -> entitlements["can_modify_quantity"]
    Return (True, "allowed") if the flag is true, else
    (False, f"user lacks permission for {action}").
    """
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
    """Provided — pretend this actually changes the order."""
    return {"order_id": order_id, "action": action, "status": "completed"}


def modify_order_gated(user_id: str, order_id: str, action: str) -> dict:
    """
    TODO 2: Call check_permission FIRST. If not allowed, return
    {"error": reason} WITHOUT calling execute_modify_order. If allowed,
    call execute_modify_order and return its result.
    """
    allowed, reason = check_permission(user_id, order_id, action)
    if not allowed:
        return {"error": reason}
    return execute_modify_order(order_id, action)


def run_turn(user_id: str, user_message: str) -> str:
    """
    TODO 3: Standard tool-use loop, but when the model calls modify_order,
    execute it via modify_order_gated(user_id, **tool_input) — NOT
    execute_modify_order directly — so the permission gate is always in
    the path. Feed the result back and return the final reply text.
    """
    system_prompt = "You are a retail support agent. Use modify_order for cancellation or quantity-change requests."
    messages = [{"role": "user", "content": user_message}]
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system_prompt,
        tools=[MODIFY_ORDER_TOOL], messages=messages
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        return next(b.text for b in response.content if b.type == "text")

    result = modify_order_gated(user_id, **tool_use.input)
    messages.append({"role": "assistant", "content": [{"type": "tool_use", "tool_use_id": tool_use.id, "content": json.dumps(result)}]})
    follow_up = client.messages.create(
        model=MODEL, max_tokens=300, system=system_prompt,
        tools=[MODIFY_ORDER_TOOL], messages=messages
    )
    return next(b.text for b in follow_up.content if b.type == "text")


if __name__ == "__main__":
    print("--- user_101 (owns ORD-500, can_cancel=True) ---")
    print("AGENT:", run_turn("user_101", "Please cancel order ORD-500."))

    print("\n--- user_202 (does not own ORD-500) ---")
    print("AGENT:", run_turn("user_202", "Please cancel order ORD-500."))
