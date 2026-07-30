"""
CAPSTONE — Banking: Full MCP Server (STARTER)

This combines three ideas from earlier this week into ONE real MCP server
(stdio transport, official `mcp` SDK — same shape as AM_H1a/PM_H1a):

  1. A plain, ungated tool           -> create_ticket           (TODO)
  2. An idempotent, audited tool     -> process_refund          (GIVEN — see note)
  3. An entitlement-GATED tool       -> dispute_transaction      (TODO)

Special note on process_refund:
  This is the exact idempotency + audit-log pattern, given to you
  COMPLETE and working. You already built this in PM_H1 — re-implementing
  it here would just be re-typing, not new learning. Read it carefully
  anyway: `audit_log()` defined here is reused by BOTH process_refund AND
  the dispute_transaction tool you're about to write, so the bank ends up
  with ONE unified audit trail across every money-moving and account
  action, not two separate logs that a reviewer has to cross-reference.

The new thing THIS lab adds: dispute_transaction() must check the calling
user's entitlements (AM_H3's pattern) BEFORE it does anything — and it has
to do that check *inside this server process*, not in the client, because
a real MCP server can't trust whichever client happens to connect to
enforce that on its behalf.

IMPORTANT design point (read before you write TODO 3):
FastMCP derives a tool's JSON schema from its Python type hints — so
because `dispute_transaction(user_id, account_id, transaction_id, reason)`
has `user_id` as a parameter, the MODEL will SEE `user_id` in its tool
schema and could try to fill it in with ANY value it wants (including
someone else's user_id, if a malicious document talks it into that — see
malicious_kb_docs.json's POL-INJECTED-2 for exactly this attack). This
server-side check_permission() is your first line of defense against that
regardless of what value shows up. Part B (client_starter.py) adds a
SECOND, independent line of defense: the client overrides whatever
user_id the model supplied with the real session's authenticated user_id
before the call ever reaches you. Two independent gates, same principle
as AM_H2's layered guardrails, now applied to identity instead of text.

Setup:
    pip install mcp
    No API key needed — this process never calls an LLM.

Run directly (for manual inspection, or to poke at it in a REPL):
    python server_starter.py
"""

import sys
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("securebank-agent")


def log(msg: str):
    # stderr, never stdout — stdout is the actual MCP JSON-RPC wire format
    # over stdio transport; printing here would corrupt it for a real client.
    print(f"[server] {msg}", file=sys.stderr, flush=True)


with open(Path(__file__).parent / "entitlements.json") as f:
    ENTITLEMENTS = json.load(f)

# --- In-memory "databases". Four independent stores, all living in THIS
# process only — a client can't read any of these directly, it has to ask
# over the protocol via get_refund_ledger()/get_dispute_ledger()/get_audit_log(),
# same as it has to ask for anything else this server knows.
TICKET_STORE: dict[str, dict] = {}
REFUND_LEDGER: list[dict] = []
PROCESSED_KEYS: dict[str, dict] = {}
DISPUTE_LEDGER: list[dict] = []
AUDIT_LOG: list[dict] = []


def audit_log(actor: str, action: str, details: dict, result: dict):
    """GIVEN — shared by process_refund AND dispute_transaction below.
    One append-only trail covering every sensitive action this server
    exposes, not one log per tool."""
    AUDIT_LOG.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "details": details,
        "result": result,
    })


@mcp.tool()
def create_ticket(subject: str, description: str, priority: str) -> dict:
    """Create a support ticket in the ticketing system.

    Args:
        subject: Short ticket subject line.
        description: Full description of the customer's issue.
        priority: One of "low", "medium", "high".
    """
    # TODO 1 (AM_H1 pattern — you've built this exact tool before):
    # Generate a ticket_id (e.g. f"TCK-{uuid.uuid4().hex[:6].upper()}"),
    # store a dict with subject, description, priority, status="open" in
    # TICKET_STORE[ticket_id], and return {"ticket_id": ticket_id, "status": "open"}.
    raise NotImplementedError


@mcp.tool()
def process_refund(transaction_id: str, amount: float, idempotency_key: str) -> dict:
    """Process a refund for a transaction. Requires an idempotency key —
    calling this twice with the SAME key returns the identical result
    without processing the refund again.

    Args:
        transaction_id: The transaction being refunded.
        amount: The refund amount.
        idempotency_key: Caller-generated key; same key on retry returns
            the same result instead of refunding twice.
    """
    # GIVEN — this is PM_H1's reference solution, verbatim. Study it: it's
    # the shape check_permission-gated dispute_transaction below will echo
    # (check first, THEN act, THEN log — never act before the check).
    if idempotency_key in PROCESSED_KEYS:
        stored_result = PROCESSED_KEYS[idempotency_key]
        audit_log("agent", "process_refund_replay",
                   {"transaction_id": transaction_id, "amount": amount, "idempotency_key": idempotency_key},
                   stored_result)
        log(f"process_refund REPLAY -> {idempotency_key}")
        return stored_result

    REFUND_LEDGER.append({"transaction_id": transaction_id, "amount": amount, "idempotency_key": idempotency_key})
    result = {"status": "refunded", "transaction_id": transaction_id, "amount": amount}
    PROCESSED_KEYS[idempotency_key] = result
    audit_log("agent", "process_refund",
              {"transaction_id": transaction_id, "amount": amount, "idempotency_key": idempotency_key},
              result)
    log(f"process_refund -> {transaction_id} (${amount})")
    return result


def check_permission(user_id: str, account_id: str) -> tuple[bool, str]:
    """
    TODO 2 (AM_H3 pattern, applied to accounts instead of orders):
    1. If user_id not in ENTITLEMENTS, return (False, "unknown user").
    2. If account_id not in ENTITLEMENTS[user_id]["owns_accounts"], return
       (False, "user does not own this account") — ownership is checked
       BEFORE the permission flag, same order as AM_H3, so a user never
       gets a "you lack permission" message for an account that was never
       theirs to begin with.
    3. If ENTITLEMENTS[user_id]["can_dispute_transaction"] is False, return
       (False, "user lacks permission to dispute transactions").
    4. Otherwise return (True, "allowed").
    """
    raise NotImplementedError


@mcp.tool()
def dispute_transaction(user_id: str, account_id: str, transaction_id: str, reason: str) -> dict:
    """File a dispute on a transaction. Only the account's owner may
    dispute a transaction on it, and only if their entitlements allow
    filing disputes at all.

    Args:
        user_id: The id of the customer this dispute is being filed for.
        account_id: The account the disputed transaction belongs to.
        transaction_id: The transaction being disputed.
        reason: Customer's stated reason for the dispute.
    """
    # TODO 3:
    #   1. Call check_permission(user_id, account_id).
    #   2. If NOT allowed: audit_log(actor=user_id, action="dispute_transaction_denied",
    #      details={"account_id":..., "transaction_id":..., "reason":...},
    #      result={"error": reason}) and return {"error": reason} WITHOUT
    #      touching DISPUTE_LEDGER.
    #   3. If allowed: generate a dispute_id (e.g.
    #      f"DSP-{uuid.uuid4().hex[:6].upper()}"), append a record to
    #      DISPUTE_LEDGER, build result = {"dispute_id": dispute_id,
    #      "status": "under_review"}, audit_log(actor=user_id,
    #      action="dispute_transaction", details=..., result=result), and
    #      return result.
    # Notice: this is the EXACT same "check first, then act, then log"
    # shape as process_refund above — the only thing that changed is WHAT
    # is being checked (an idempotency key vs. an ownership+flag pair).
    raise NotImplementedError


@mcp.tool()
def get_refund_ledger() -> list[dict]:
    """Return the refund ledger — one entry per refund actually processed
    (idempotent replays never add an entry here)."""
    return REFUND_LEDGER


@mcp.tool()
def get_dispute_ledger() -> list[dict]:
    """Return the dispute ledger — one entry per dispute actually filed
    (denied attempts never add an entry here, but they ARE in the audit log)."""
    return DISPUTE_LEDGER


@mcp.tool()
def get_audit_log() -> list[dict]:
    """Return the full audit trail — every process_refund and
    dispute_transaction call, allowed or denied, fresh or replayed, each
    attributed and timestamped."""
    return AUDIT_LOG


if __name__ == "__main__":
    log("securebank-agent MCP server starting — stdio transport, waiting for a client to connect...")
    log("(this will sit here silently until a client sends it something over stdin — that's normal, not a hang)")
    mcp.run(transport="stdio")
    log("server stopped")

# Once TODO 1-3 are done, verify standalone (no client, no LLM, no cost):
# drop into a REPL, `import server_starter as s`, and call:
#   s.create_ticket("test", "test", "low")                     -> ticket created
#   s.dispute_transaction("user_101", "ACC-9001", "TXN-1", "x") -> allowed, dispute filed
#   s.dispute_transaction("user_202", "ACC-9001", "TXN-1", "x") -> denied, ACC-9001 isn't user_202's
#   s.dispute_transaction("user_202", "ACC-9003", "TXN-2", "x") -> denied, user_202 can't dispute at all
#   s.get_audit_log()                                            -> all four attempts, attributed
