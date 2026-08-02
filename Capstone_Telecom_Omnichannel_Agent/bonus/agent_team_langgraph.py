# -*- coding: utf-8 -*-
"""
BONUS TIER C - Alt-Stack Reimplementation: LangGraph

There is NO solution file for this part. Same StateGraph conventions as
Day2/HandsOnExercise/AM_H2_insurance_supervisor/solution_langgraph.py
(TypedDict state, nodes as functions, add_conditional_edges for routing) -
read that file first if you haven't, this scaffold assumes its shape.

THE CONSTRAINT THAT MAKES THIS A REAL EXERCISE, NOT BUSYWORK: this graph
must talk to the SAME unmodified starter/mcp_server.py (spawn it exactly
the way agent_team.py does) and reuse starter/permissions.py,
starter/guardrails.py, and starter/cost.py AS-IS, unmodified. Only the
orchestration layer (supervisor loop + specialist loop -> a graph) is
allowed to change. If you find yourself editing mcp_server.py or
permissions.py to make this easier, that's a sign the constraint is
teaching you something about where enforcement actually lives - stop and
think about why, rather than patching around it.

Setup:
    pip install langgraph langchain-anthropic mcp
    Uses the same ANTHROPIC_API_KEY already in .env.

This file is a SCAFFOLD, not a working implementation - the graph is
wired, the state is typed, and the MCP connection is bootstrapped exactly
like agent_team.py's, but the node bodies (where tool-calling actually
happens) are marked TODO. There's no NotImplementedError here because
this whole file is optional - fill in what you want to explore.
"""

import asyncio
import sys
from pathlib import Path
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

_STARTER_DIR = Path(__file__).resolve().parent.parent / "starter"
if _STARTER_DIR.exists() and str(_STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(_STARTER_DIR))

# Reuse Part 2/5/6 UNCHANGED - the whole point of this exercise.
from permissions import load_entitlements  # noqa: E402
from guardrails import sanitize_retrieved_docs, output_guardrail  # noqa: E402
from cost import cost_report  # noqa: E402

MODEL = "claude-sonnet-5"
llm = ChatAnthropic(model=MODEL, max_tokens=700)

SERVER_SCRIPT = _STARTER_DIR / "mcp_server.py"


class TeamState(TypedDict):
    """Same idea as AM_H2's RoutingState, extended for a tool-using,
    multi-turn specialist instead of a single classify-and-reply node.

    TODO: you'll likely want more fields here once you start
    implementing the specialist nodes - e.g. a running message history
    per specialist, the customer's session context (customer_id,
    owned_accounts, agent_role), and the retrieved/allowed doc_ids
    guardrails.output_guardrail() needs at the end.
    """
    message: str
    specialist: Literal["billing", "plans", "tech_support", ""]
    reply: str


def classify_node(state: TeamState) -> dict:
    """TODO: same idea as agent_team.HANDOFF_TOOL, but expressed as a
    LangGraph routing decision instead of an Anthropic tool call. Decide
    whether this needs billing/plans/tech_support at all, or whether the
    supervisor can answer directly (a greeting) - if you want that
    escape hatch, you'll need a 4th state/route for it.
    """
    raise NotImplementedError(
        "TODO (optional, bonus): classify the message the same way "
        "agent_team.SUPERVISOR_SYSTEM + HANDOFF_TOOL do."
    )


def billing_node(state: TeamState) -> dict:
    """TODO: reimplement agent_team.run_specialist("billing", ...) as a
    graph node. You'll need to, inside this node: open (or reuse) the
    MCP ClientSession to starter/mcp_server.py, call search_kb, run the
    result through guardrails.sanitize_retrieved_docs(), call
    apply_billing_credit through the SAME identity-overwrite discipline
    as agent_team.secure_call_tool() (don't skip this just because it's
    a different framework - re-read that function's docstring), and run
    the final reply through guardrails.output_guardrail() before
    returning it.
    """
    raise NotImplementedError("TODO (optional, bonus): implement the billing specialist node.")


def plans_node(state: TeamState) -> dict:
    """TODO: same shape as billing_node, scoped to plans_agent's tools."""
    raise NotImplementedError("TODO (optional, bonus): implement the plans specialist node.")


def tech_node(state: TeamState) -> dict:
    """TODO: same shape as billing_node, scoped to tech_agent's tools."""
    raise NotImplementedError("TODO (optional, bonus): implement the tech_support specialist node.")


def route_on_specialist(state: TeamState) -> Literal["billing", "plans", "tech_support"]:
    return state["specialist"]


# ---------- Wiring the graph (given shape, same pattern as AM_H2) ----------
graph_builder = StateGraph(TeamState)
graph_builder.add_node("classify", classify_node)
graph_builder.add_node("billing", billing_node)
graph_builder.add_node("plans", plans_node)
graph_builder.add_node("tech_support", tech_node)

graph_builder.set_entry_point("classify")
graph_builder.add_conditional_edges("classify", route_on_specialist, {
    "billing": "billing",
    "plans": "plans",
    "tech_support": "tech_support",
})
graph_builder.add_edge("billing", END)
graph_builder.add_edge("plans", END)
graph_builder.add_edge("tech_support", END)

graph = graph_builder.compile()


async def main():
    server_params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            print(f"[Connected to {SERVER_SCRIPT.name} - "
                  f"{len((await mcp_session.list_tools()).tools)} tools discovered]")

            # TODO: thread mcp_session into the graph state/nodes above,
            # then invoke it, e.g.:
            #   result = graph.invoke({"message": "...", "specialist": "", "reply": ""})
            #   print(result["reply"])
            print("\nScaffold connected successfully. Implement the node bodies above to continue.")
            print(cost_report())  # given cost.py works unmodified regardless of orchestration layer


if __name__ == "__main__":
    asyncio.run(main())

# Discussion questions (bring back to the group, per bonus/README.md):
#   - Which hand-written gate in agent_team.py (secure_call_tool's role
#     allowlist? the identity overwrite? the idempotency-key derivation?)
#     did you have to reimplement here verbatim, versus which did
#     LangGraph give you "for free" via some built-in mechanism? Be
#     specific - "LangGraph handles security" is not an answer.
#   - Does the StateGraph make the supervisor->specialist handoff easier
#     or harder to reason about than agent_team.py's plain
#     execute_handoff() function? What did you gain, what did you lose?
