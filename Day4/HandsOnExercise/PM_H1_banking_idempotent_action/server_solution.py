"""
PM · H1a — Banking: Idempotent, Audited Refund Server (REFERENCE SOLUTION)

Builds on AM_H1's MCP server pattern (same @mcp.tool() shape, same stdio
transport) — what's NEW here is the production concern, not the protocol:
idempotency and an append-only audit log both live in THIS process, not
the client's. That placement is deliberate, not incidental — a network
retry re-invokes the external system (this server), not whichever agent
process happened to be running when the first attempt was made. AM_H1's
ticketing tool could get away with living in-process because a duplicate
ticket is a UX nit; process_refund moves money, so a client-side retry
that double-processes is a real financial bug.

Setup:
    pip install mcp
    No API key needed — this process never calls an LLM.

Run directly (for manual inspection):
    python server_solution.py
"""

import sys
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("banking-refunds")


def log(msg: str):
    # stderr, never stdout — stdout is the actual MCP JSON-RPC wire format
    # over stdio transport; printing here would corrupt it for a real client.
    print(f"[server] {msg}", file=sys.stderr, flush=True)


REFUND_LEDGER: list[dict] = []
PROCESSED_KEYS: dict[str, dict] = {}
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


@mcp.tool()
def get_ledger() -> list[dict]:
    """Return the refund ledger — one entry per refund actually processed
    (idempotent replays never add an entry here)."""
    return REFUND_LEDGER


@mcp.tool()
def get_audit_log() -> list[dict]:
    """Return the full audit trail — every process_refund call, both
    fresh processing and idempotent replays, each attributed and
    timestamped."""
    return AUDIT_LOG


if __name__ == "__main__":
    log("banking-refunds MCP server starting — stdio transport, waiting for a client to connect...")
    log("(this will sit here silently until a client sends it something over stdin — that's normal, not a hang)")
    mcp.run(transport="stdio")
    log("server stopped")

# Notice REFUND_LEDGER/PROCESSED_KEYS/AUDIT_LOG live in THIS process only.
# The client (client_solution.py) can't read them directly — it has to ask
# over the protocol, via get_ledger()/get_audit_log(), same as it has to
# ask for anything else this server knows. That boundary IS the point.
