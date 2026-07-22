# AM · H3 — Retail: Enforce Per-User Permissions on an Action

**Track:** Retail | **Time box:** ~20 min | **Pattern practiced:** entitlement checks gate tool execution — the agent acts only within the customer's own rights

## Scenario
A retail agent has a `modify_order` tool. Every customer who chats in can
ask the agent to change an order — but not every customer is entitled to
every change. A guest-checkout customer might only be able to cancel their
own order; a logged-in loyalty member might be able to modify item
quantities; nobody should be able to modify someone else's order at all.
Today the permission check happens in your code, gating the tool — not as
something the model decides on its own.

## Your task
1. `ENTITLEMENTS` (provided) — a dict of `user_id -> {"owns_orders":
   [...], "can_modify_quantity": bool, "can_cancel": bool}`.
2. `check_permission(user_id, order_id, action)` — look up the user's
   entitlements. First check `order_id in entitlements["owns_orders"]`
   (a user can never act on an order they don't own, regardless of any
   other permission). Then check the specific action-level permission
   (`can_modify_quantity` for `"modify_quantity"`, `can_cancel` for
   `"cancel"`). Return `(allowed: bool, reason: str)`.
3. A `modify_order` tool + agent loop where, BEFORE your code executes the
   actual order-modification logic, it calls `check_permission`. If not
   allowed, return a clear refusal as the tool result (so the model relays
   it naturally) — never let the model's own judgment be the only gate.
4. Run the same request ("cancel order ORD-500") as two different users —
   one entitled, one not — and confirm the permission check produces
   different outcomes for identical requests.

## Why this matters
This is today's Topic 05 (identity & permissions). The critical design
point: the permission check happens in **your code**, deterministically,
before the action executes — not as an instruction in the system prompt
that the model might follow. A system prompt saying "only let users modify
their own orders" is a suggestion; a `check_permission` call your code
runs unconditionally is a guarantee.

## Files
- `entitlements.json` — sample user entitlements and order ownership.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a manager role that can act on ANY order regardless of
  `owns_orders`, and make sure your `check_permission` logic handles the
  "role override" case without duplicating the ownership check everywhere.
- Log every permission check (user, order, action, allowed/denied) — the
  seed of an access-control audit trail, previewed further this afternoon.

## Discussion (bring back to the group)
- What's the difference in risk between the model REFUSING an unauthorized
  request because it reasoned its way there, vs. the tool call being
  structurally blocked by `check_permission`? Can you construct a prompt
  that might talk the model out of refusing, if refusal were its only line
  of defense?
