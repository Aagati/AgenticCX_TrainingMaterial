"""
AM · H1b — Banking: Use an MCP Server (REFERENCE SOLUTION)

An agent tool-use loop where the tools don't live in this process — they
live in a separate process (server_solution.py) and are called over the
real MCP protocol: this process spawns the server over stdio, discovers
its tools via session.list_tools() (no hardcoded schema — the server is
the only source of truth), and executes them via session.call_tool().
This is "swap in a real MCP server later" made real: any MCP-compatible
agent could point at that same server process without custom integration
code, because the wire protocol — not a shared Python import — is the
contract.

Setup:
    pip install mcp
    Uses ANTHROPIC_API_KEY (already in .env) — no new key needed.
    Just run this file directly; it launches server_solution.py itself.
"""

import asyncio
import json
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a banking support agent. When a customer reports
an issue that needs follow-up, use create_ticket with a clear subject,
description, and appropriate priority. Tell the customer their ticket
number. If a later message confirms the issue is resolved, use
resolve_ticket with a brief resolution note."""

SERVER_SCRIPT = Path(__file__).parent / "server_solution.py"


def mcp_tool_to_anthropic_schema(mcp_tool) -> dict:
    """MCP's list_tools() is the schema's only source of truth — no
    hand-maintained CREATE_TICKET_TOOL dict like in solution.py."""
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description or "",
        "input_schema": mcp_tool.inputSchema,
    }


async def run_turn(session: ClientSession, tools: list, messages: list) -> list:
    response = client.messages.create(
        model=MODEL, max_tokens=400, system=SYSTEM_PROMPT,
        tools=tools, messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use is None:
        text = next(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": text})
        return messages

    # The actual call crosses process boundaries over MCP's stdio transport.
    mcp_result = await session.call_tool(tool_use.name, tool_use.input)
    result_text = "".join(
        block.text for block in mcp_result.content if hasattr(block, "text")
    )

    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": result_text}
    ]})

    followup = client.messages.create(
        model=MODEL, max_tokens=300, system=SYSTEM_PROMPT,
        tools=tools, messages=messages,
    )
    text = next(b.text for b in followup.content if b.type == "text")
    messages.append({"role": "assistant", "content": text})
    return messages


async def main():
    server_params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER_SCRIPT)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            tools = [mcp_tool_to_anthropic_schema(t) for t in mcp_tools]
            print(f"[Discovered {len(tools)} tools over MCP: "
                  f"{[t['name'] for t in tools]}]\n")

            convo = [{"role": "user", "content":
                      "My transfer to my landlord failed and the money hasn't come back yet."}]
            convo = await run_turn(session, tools, convo)
            print("AGENT:", convo[-1]["content"])

            convo.append({"role": "user", "content":
                          "Update — the money just came back on its own, you can close it out."})
            convo = await run_turn(session, tools, convo)
            print("AGENT:", convo[-1]["content"])


if __name__ == "__main__":
    asyncio.run(main())

# Expected: ticket created, then resolved — but `tools` here was never
# hand-written, it came from session.list_tools() talking to a separate OS
# process over stdio. Kill server_solution.py's process independently,
# point this client at a different MCP server, or run the server
# standalone under any other MCP-compatible agent — none of that is
# possible if the tools were plain in-process Python functions.
