"""
Standalone MCP server for the Day 4 Banking lab (H1) — the ticketing "system of record".

Runs as its own OS process, launched by the agent via stdio (see the notebook's
`mcp_servers={"ticketing": {"type": "stdio", "command": ..., "args": [...]}}` config).
This is deliberately NOT `create_sdk_mcp_server` (the in-process pattern used in every
tool from Day 1-3) — it is a genuinely separate process speaking the real MCP protocol
over stdin/stdout, exactly like a production ticketing integration would be.

The backend here is a plain in-memory dict, not a real Zendesk/ServiceNow account —
that part is intentionally mocked. What is real is the process boundary and the MCP
wire protocol crossing it; that boundary is the only part of "MCP integration" this
curriculum can teach without a trainee's own SaaS credentials.

Idempotency + an append-only, server-owned audit log live HERE, not in the agent
process — so the audit trail is structurally external to the agent that requested the
action, the same "verify from outside" property Day 3's CompliantCallFlow audit_log had,
now one process boundary further out.
"""

import time
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ticketing")

# tickets: ticket_id -> {subject, body, status, created_ts, resolution}
tickets: dict[str, dict] = {}

# idempotency_key -> ticket_id, for create_ticket retries
_create_keys: dict[str, str] = {}
# idempotency_key -> ticket_id, for resolve_ticket retries (keyed separately: a create
# key and a resolve key for the SAME ticket must not collide)
_resolve_keys: dict[str, str] = {}

# Append-only. This IS the replayable audit trail — reconstructible from this list
# alone, independent of the `tickets` dict's current (mutable) state.
audit_log: list[dict] = []


def _log(ticket_id: str, event: str, **details):
    entry = {"ticket_id": ticket_id, "event": event, "ts": time.time(), **details}
    audit_log.append(entry)
    return entry


@mcp.tool()
def create_ticket(subject: str, body: str, idempotency_key: str) -> dict:
    """Create a support ticket. Safe to retry: calling this twice with the SAME
    idempotency_key returns the ALREADY-CREATED ticket, never a duplicate."""
    # Precedence 1: this exact key already created a ticket -> return the existing one.
    # This is what makes a network retry (agent never saw the first response) safe.
    if idempotency_key in _create_keys:
        existing_id = _create_keys[idempotency_key]
        return {"ticket_id": existing_id, "status": tickets[existing_id]["status"],
                "note": "already created (idempotent replay)"}

    ticket_id = f"TCK-{len(tickets) + 1000}"
    tickets[ticket_id] = {
        "subject": subject, "body": body, "status": "open",
        "created_ts": time.time(), "resolution": None,
    }
    _create_keys[idempotency_key] = ticket_id
    _log(ticket_id, "created", subject=subject, idempotency_key=idempotency_key)
    return {"ticket_id": ticket_id, "status": "open", "note": "created"}


@mcp.tool()
def resolve_ticket(ticket_id: str, resolution: str, idempotency_key: str) -> dict:
    """Resolve an open ticket. 'resolved' is a terminal state: resolving twice with the
    same resolution is a safe no-op; resolving with a DIFFERENT resolution than what's
    already on file is a conflict, not a silent overwrite; resolving a ticket that was
    never created fails safely instead of crashing."""
    # Precedence 1: unknown ticket -> fail safely, no exception, no mutation.
    if ticket_id not in tickets:
        return {"ticket_id": ticket_id, "status": "error",
                "note": "no such ticket — cannot resolve what was never created"}

    record = tickets[ticket_id]

    # Precedence 2: this exact key already resolved this ticket -> idempotent replay.
    if idempotency_key in _resolve_keys and _resolve_keys[idempotency_key] == ticket_id:
        return {"ticket_id": ticket_id, "status": record["status"],
                "resolution": record["resolution"], "note": "already resolved (idempotent replay)"}

    # Precedence 3: already resolved under a DIFFERENT key/resolution -> conflict, refuse
    # to silently overwrite a resolution someone else already committed.
    if record["status"] == "resolved":
        if record["resolution"] == resolution:
            # Same outcome, different key (e.g. two independent retries) — still a safe no-op.
            return {"ticket_id": ticket_id, "status": "resolved",
                    "resolution": record["resolution"], "note": "already resolved (same outcome)"}
        return {"ticket_id": ticket_id, "status": "conflict",
                "note": f"already resolved with a different resolution: {record['resolution']!r}"}

    # Only reachable for a genuinely open ticket, new resolve attempt.
    record["status"] = "resolved"
    record["resolution"] = resolution
    _resolve_keys[idempotency_key] = ticket_id
    _log(ticket_id, "resolved", resolution=resolution, idempotency_key=idempotency_key)
    return {"ticket_id": ticket_id, "status": "resolved", "resolution": resolution, "note": "resolved"}


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Look up a ticket's current state."""
    record = tickets.get(ticket_id)
    if not record:
        return {"ticket_id": ticket_id, "status": "error", "note": "no such ticket"}
    return {"ticket_id": ticket_id, **record}


@mcp.tool()
def replay_ticket(ticket_id: str) -> dict:
    """Reconstruct a ticket's lifecycle from the server's audit log alone — independent
    of the current `tickets` dict — the same replayability guarantee Day 3's
    replay_final_state gave for compliance, applied here to a transactional action."""
    events = [e["event"] for e in audit_log if e["ticket_id"] == ticket_id]
    return {
        "ticket_id": ticket_id,
        "was_created": "created" in events,
        "was_resolved": "resolved" in events,
        "event_count": len(events),
        "events": events,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
