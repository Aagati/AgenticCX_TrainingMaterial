"""
AM · H1a — Banking: Build an MCP Server (STARTER)

A real MCP server (stdio transport, via the official `mcp` Python SDK's
FastMCP) exposing create_ticket / resolve_ticket as MCP tools. Once this
is working, client_starter.py (Part B) spawns THIS file as a subprocess
and talks to it over the real MCP protocol.

Setup:
    pip install mcp
    No new API key needed — this process never calls an LLM, it just
    serves tools over the MCP protocol.

Run directly (for manual inspection with an MCP-compatible client/inspector):
    python server_starter.py
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
    # TODO 1: Generate a ticket_id (e.g. f"TCK-{uuid.uuid4().hex[:6].upper()}"),
    # store a dict with subject, description, priority, status="open",
    # resolution_note=None in TICKET_STORE[ticket_id], and return
    # {"ticket_id": ticket_id, "status": "open"}.
    raise NotImplementedError


@mcp.tool()
def resolve_ticket(ticket_id: str, resolution_note: str) -> dict:
    """Mark a ticket as resolved with a resolution note.

    Args:
        ticket_id: The ticket id returned by create_ticket.
        resolution_note: A brief note on how the issue was resolved.
    """
    # TODO 2: If ticket_id not in TICKET_STORE, return {"error": "ticket not found"}.
    # Otherwise set status="resolved" and resolution_note, then return
    # {"ticket_id": ticket_id, "status": "resolved"}.
    raise NotImplementedError


if __name__ == "__main__":
    log("banking-ticketing MCP server starting — stdio transport, waiting for a client to connect...")
    log("(this will sit here silently until a client sends it something over stdin — that's normal, not a hang)")
    mcp.run(transport="stdio")
    log("server stopped")

# Notice create_ticket/resolve_ticket are registered with @mcp.tool()
# instead of a hand-written CREATE_TICKET_TOOL/RESOLVE_TICKET_TOOL JSON
# schema dict — FastMCP derives the schema from the type hints and
# docstring above. Any MCP-compatible client (Part B's client_starter.py,
# or Claude Desktop, or any other agent) can discover and call these
# tools without knowing this file exists.
