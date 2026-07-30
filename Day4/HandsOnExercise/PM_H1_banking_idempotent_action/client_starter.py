"""
PM · H1b — Banking: Idempotent, Audited Refund Client (STARTER)

The MCP mechanics here (spawn the server, discover its tools, call them
over the protocol) are the same ones you built in AM_H1b — given below as
working boilerplate so your effort goes into the ONE new piece: simulating
a network retry by calling process_refund a SECOND time, directly, with
the exact same idempotency_key the model used the first time, and
confirming the server dedupes it instead of refunding twice.

Setup:
    pip install mcp
    Uses ANTHROPIC_API_KEY (already in .env) — no new key needed.
    Complete Part A (server_starter.py) first — this file spawns it.
    Just run this file directly; it launches server_starter.py itself.
"""

import asyncio
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

SYSTEM_PROMPT = """You are a banking support agent. When a customer
requests a refund, use process_refund with a fresh, unique idempotency_key
you generate yourself (e.g. a random-looking string) for this specific
customer request."""

SERVER_SCRIPT = Path(__file__).parent / "server_starter.py"


def mcp_tool_to_anthropic_schema(mcp_tool) -> dict:
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description or "",
        "input_schema": mcp_tool.inputSchema,
    }


def mcp_text(mcp_result) -> str:
    # FastMCP serializes a returned list[dict] as one content block per
    # list item, not one block containing a JSON array — join with a
    # separator or multi-entry results (like get_audit_log) print as one
    # unreadable run-on blob.
    return "\n".join(block.text for block in mcp_result.content if hasattr(block, "text"))


async def run_turn(session: ClientSession, tools: list, messages: list):
    """Given — same shape as AM_H1b's run_turn. Returns (messages, tool_input)
    where tool_input is the exact args the model passed to process_refund
    (None if it didn't call a tool this turn) — Part B's TODO needs those
    args to replay the SAME call."""
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=SYSTEM_PROMPT,
        tools=tools, messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)

    if tool_use is None:
        text = next(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": text})
        return messages, None

    mcp_result = await session.call_tool(tool_use.name, tool_use.input)
    result_text = mcp_text(mcp_result)

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
    return messages, tool_use.input


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
                      "I was double-charged $45 for order #8821, please refund the duplicate charge."}]
            convo, used_args = await run_turn(session, tools, convo)
            print("AGENT:", convo[-1]["content"])

            if used_args:
                # TODO: Simulate a network retry — call
                # `await session.call_tool("process_refund", used_args)` a
                # SECOND time, directly, bypassing the model entirely (this
                # is what a raw HTTP client retry looks like: same request,
                # no LLM in the loop). Print the raw result text. It should
                # be IDENTICAL to what the first call returned, and
                # get_ledger() below should still show only one entry.
                raise NotImplementedError

            ledger = await session.call_tool("get_ledger", {})
            audit = await session.call_tool("get_audit_log", {})
            print("\n[REFUND_LEDGER]:", mcp_text(ledger))
            print("\n[AUDIT_LOG]:", mcp_text(audit))


if __name__ == "__main__":
    asyncio.run(main())

# Expected: REFUND_LEDGER has exactly ONE entry even though process_refund
# was called twice. AUDIT_LOG has TWO entries: "process_refund" then
# "process_refund_replay" — both timestamped and attributed. Both lists
# come from get_ledger()/get_audit_log() over MCP, not from a local dict —
# this process never held that state to begin with.
