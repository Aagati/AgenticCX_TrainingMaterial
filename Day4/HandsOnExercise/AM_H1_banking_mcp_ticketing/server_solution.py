"""
AM · H1a — Banking: Build an MCP Server (REFERENCE SOLUTION)

A real MCP server (stdio transport, via the official `mcp` Python SDK's
FastMCP) exposing create_ticket / resolve_ticket as MCP tools. Run it
standalone to inspect, or let client_starter.py/client_solution.py spawn
it as a subprocess.

Setup:
    pip install mcp (=> FastMCP - Python's SDK for building MCPs)
    No new API key needed — this process never calls an LLM, it just
    serves tools over the MCP protocol.

Run directly (for manual inspection with an MCP-compatible client/inspector):
    python server_solution.py
"""

import sys
import uuid
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("banking-ticketing")


def log(msg: str):
    # stderr, never stdout — stdout is the actual MCP JSON-RPC wire format
    # over stdio transport; printing here would corrupt it for a real client.
    print(f"[server] {msg}", file=sys.stderr, flush=True)

TICKET_STORE: dict[str, dict] = {}


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
        "subject": subject, "description": description, "priority": priority,
        "status": "open", "resolution_note": None,
    }
    log(f"create_ticket called -> {ticket_id} ({priority})")
    return {"ticket_id": ticket_id, "status": "open"}


@mcp.tool()
def resolve_ticket(ticket_id: str, resolution_note: str) -> dict:
    """Mark a ticket as resolved with a resolution note.

    Args:
        ticket_id: The ticket id returned by create_ticket.
        resolution_note: A brief note on how the issue was resolved.
    """
    if ticket_id not in TICKET_STORE:
        log(f"resolve_ticket called -> {ticket_id} NOT FOUND")
        return {"error": "ticket not found"}
    TICKET_STORE[ticket_id]["status"] = "resolved"
    TICKET_STORE[ticket_id]["resolution_note"] = resolution_note
    log(f"resolve_ticket called -> {ticket_id} resolved")
    return {"ticket_id": ticket_id, "status": "resolved"}


if __name__ == "__main__":
    log("banking-ticketing MCP server starting — stdio transport, waiting for a client to connect...")
    log("(this will sit here silently until a client sends it something over stdin — that's normal, not a hang)")
    mcp.run(transport="stdio")
    log("server stopped")

# Notice create_ticket/resolve_ticket are registered with @mcp.tool()
# instead of a hand-written CREATE_TICKET_TOOL/RESOLVE_TICKET_TOOL JSON
# schema dict — FastMCP derives the schema from the type hints and
# docstring. Any MCP-compatible client (this repo's client_starter.py, or
# Claude Desktop, or any other agent) can now discover and call these
# tools without knowing this file exists.
