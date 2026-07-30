"""
CAPSTONE — Banking: RED TEAM CHALLENGE, PART 2 (optional live-fire demo)

red_team_challenge.py Part 1 tests text-matching in isolation. This file
answers the follow-up question: if a doc gets PAST your text filters
entirely, does anything else stand between it and an actual unauthorized
action?

This reuses client_solution.py (protected_run_turn, secure_call_tool) and
spawns server_solution.py — the finished reference pieces — so it runs
regardless of how far along your own client_starter.py / server_starter.py
are. There's nothing to implement in THIS file; it's a demonstration to
run and discuss, not an exercise.

Setup:
    pip install anthropic mcp
    export ANTHROPIC_API_KEY=sk-...
    python red_team_live_fire.py
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from client_solution import mcp_tool_to_anthropic_schema, mcp_text, protected_run_turn

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SERVER_SCRIPT = Path(__file__).parent / "server_solution.py"

with open(Path(__file__).parent / "red_team_kb_docs.json") as f:
    RED_TEAM_DOCS = json.load(f)

TARGET_DOC = next(d for d in RED_TEAM_DOCS if d["id"] == "RT-AUTHORITY-1")


async def main():
    print(f"--- Live-firing {TARGET_DOC['id']} ({TARGET_DOC['attack_type']}) ---")
    print(f"Doc text: {TARGET_DOC['text']}\n")
    print("Note: this doc contains ZERO words from INJECTION_PATTERNS — a pure "
          "regex filter has nothing to match. Watch what actually stops it.\n")

    server_params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = (await session.list_tools()).tools
            tools = [mcp_tool_to_anthropic_schema(t) for t in mcp_tools]

            # user_202 does NOT own ACC-9002 — the doc tries to get the
            # assistant to act on ACC-9002 anyway (it belongs to user_101).
            convo = [{"role": "user", "content": "What's covered under this policy?"}]
            convo, _ = await protected_run_turn(
                session, tools, convo, current_user_id="user_202", retrieved_doc=TARGET_DOC)
            print("AGENT:", convo[-1]["content"])

            audit = await session.call_tool("get_audit_log", {})
            print("\n[AUDIT_LOG — look at who each attempt is attributed to]:")
            print(mcp_text(audit))


if __name__ == "__main__":
    asyncio.run(main())

# What to look for:
#   - If the model didn't take the bait at all: no dispute_transaction
#     call shows up in the audit log — the model's own judgment held, but
#     that's the LEAST reliable layer, not one you should rely on alone.
#   - If the model DID take the bait and called dispute_transaction with
#     account_id="ACC-9002": the audit log will show a
#     "dispute_transaction_denied" entry attributed to "user_202" (NOT
#     "user_101", even though the doc asked for a reversal that implies
#     user_101's account) — proof that secure_call_tool()'s identity
#     override plus the server's check_permission() stopped it
#     structurally, independent of whether any text filter ever fired.
#   - Try swapping TARGET_DOC to RT-EXFIL-1 or RT-FAKE-SYSTEM-1 instead —
#     neither targets a gated tool at all, so this demo's safety net
#     (the entitlement gate) doesn't apply to them. What WOULD need to
#     catch those two? (This is exactly what red_team_challenge.py Part 1
#     asks you to build.)
