"""
CAPSTONE — Banking: Full MCP Server (REFERENCE SOLUTION)

See server_starter.py for the full walkthrough. Summary of what's below:
  - create_ticket           -> plain, ungated tool (AM_H1 pattern)
  - process_refund          -> idempotent + audited, GIVEN complete (PM_H1 pattern)
  - dispute_transaction     -> entitlement-GATED tool (AM_H3 pattern, server-side)
  - get_refund_ledger / get_dispute_ledger / get_audit_log -> read-only introspection

Setup:
    pip install mcp
    No API key needed — this process never calls an LLM.

Run directly (for manual inspection):
    python server_solution.py
"""

import sys
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("securebank-agent")


def log(msg: str):
    print(f"[server] {msg}", file=sys.stderr, flush=True)


with open(Path(__file__).parent / "entitlements.json") as f:
    ENTITLEMENTS = json.load(f)

TICKET_STORE: dict[str, dict] = {}
REFUND_LEDGER: list[dict] = []
PROCESSED_KEYS: dict[str, dict] = {}
DISPUTE_LEDGER: list[dict] = []
AUDIT_LOG: list[dict] = []


def audit_log(actor: str, action: str, details: dict, result: dict):
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
    ticket_id = f"TCK-{uuid.uuid4().hex[:6].upper()}"
    TICKET_STORE[ticket_id] = {
        "subject": subject, "description": description,
        "priority": priority, "status": "open",
    }
    log(f"create_ticket -> {ticket_id} ({priority})")
    return {"ticket_id": ticket_id, "status": "open"}


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
    if user_id not in ENTITLEMENTS:
        return False, "unknown user"
    entitlements = ENTITLEMENTS[user_id]
    if account_id not in entitlements["owns_accounts"]:
        return False, "user does not own this account"
    if not entitlements["can_dispute_transaction"]:
        return False, "user lacks permission to dispute transactions"
    return True, "allowed"


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
    allowed, reason_msg = check_permission(user_id, account_id)
    details = {"account_id": account_id, "transaction_id": transaction_id, "reason": reason}

    if not allowed:
        result = {"error": reason_msg}
        audit_log(user_id, "dispute_transaction_denied", details, result)
        log(f"dispute_transaction DENIED -> {user_id}/{account_id}: {reason_msg}")
        return result

    dispute_id = f"DSP-{uuid.uuid4().hex[:6].upper()}"
    DISPUTE_LEDGER.append({"dispute_id": dispute_id, "user_id": user_id, **details})
    result = {"dispute_id": dispute_id, "status": "under_review"}
    audit_log(user_id, "dispute_transaction", details, result)
    log(f"dispute_transaction -> {dispute_id} ({user_id}/{account_id})")
    return result


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

# Expected standalone checks:
#   dispute_transaction("user_101", "ACC-9001", "TXN-1", "x") -> allowed (owns it, can_dispute=True)
#   dispute_transaction("user_202", "ACC-9001", "TXN-1", "x") -> denied, "user does not own this account"
#   dispute_transaction("user_202", "ACC-9003", "TXN-2", "x") -> denied, "user lacks permission to dispute transactions"
#   process_refund called twice with the same idempotency_key -> REFUND_LEDGER grows once, AUDIT_LOG grows twice
