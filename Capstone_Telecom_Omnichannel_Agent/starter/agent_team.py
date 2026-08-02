# -*- coding: utf-8 -*-
"""
CAPSTONE - Telecom: Multi-Agent Team over MCP

THE PATTERN: a supervisor that delegates to tool-using specialist
sub-agents (Day2 PM_H1's shape), where every specialist's tools are
real MCP tools served by mcp_server.py (Day4's shape) - gated by
permissions.py's two-dimensional entitlement check, defended by
guardrails.py's layered input/output checks, and every model call priced
and traced through cost.py + Langfuse (Day5's shape, extended with
actual cost tracking).

secure_call_tool() is the load-bearing function: it's what makes
multi-agent + permissions + injection-defense work TOGETHER instead of
side by side - see its docstring.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from permissions import load_entitlements
from guardrails import sanitize_retrieved_docs, output_guardrail, log_step
from cost import record_usage, cost_report

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

SERVER_SCRIPT = Path(__file__).parent / "mcp_server.py"

# ----------------------------------------------------------------------
# Observability: every specialist turn and the supervisor's own turn are
# traced to Langfuse - same traced()-no-op-if-unconfigured pattern as
# Day5's lab30, so this stays runnable with zero Langfuse keys. What's
# new here versus every other Langfuse use in the course: cost.py's
# record_usage() (called from inside run_specialist/run_turn below) logs
# actual token cost per call, not just quality scores.
# ----------------------------------------------------------------------
_LANGFUSE_ENABLED = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
)
if _LANGFUSE_ENABLED:
    from langfuse import Langfuse, observe
    langfuse = Langfuse()
else:
    langfuse = None


def traced(**observe_kwargs):
    """@observe if Langfuse keys are configured, otherwise a no-op decorator."""
    if _LANGFUSE_ENABLED:
        return observe(**observe_kwargs)
    return lambda fn: fn


def _set_trace_session(session_id: str) -> None:
    """Best-effort: tag the current trace with this conversation's
    session_id, so every turn of one conversation groups together in the
    Langfuse Sessions view even though each run_turn() call is its own
    trace. Falls back to span metadata if the installed langfuse
    client's update_current_trace() doesn't accept session_id as
    written - confirm the exact call against your installed
    langfuse==4.14.1 before relying on it in a real deployment."""
    if langfuse is None:
        return
    try:
        langfuse.update_current_trace(session_id=session_id)
    except (AttributeError, TypeError):
        langfuse.update_current_span(metadata={"session_id": session_id})


# ----------------------------------------------------------------------
# MCP client plumbing (given) - same shape as Day4's capstone client:
# discover tools live via list_tools(), no hardcoded schema client-side.
# ----------------------------------------------------------------------
def mcp_tool_to_anthropic_schema(mcp_tool) -> dict:
    return {"name": mcp_tool.name, "description": mcp_tool.description or "", "input_schema": mcp_tool.inputSchema}


def mcp_text(mcp_result) -> str:
    return "\n".join(block.text for block in mcp_result.content if hasattr(block, "text"))


def mcp_json_list(mcp_result) -> list[dict]:
    """FastMCP serializes a tool's `list[dict]` return as ONE content
    block PER LIST ITEM, not one block holding a JSON array (the same
    gotcha Day4's PM_H1 lab documents for get_audit_log). json.loads()-ing
    mcp_text()'s newline-joined blocks would either throw on 2+ items
    (multiple concatenated top-level JSON values) or - worse - silently
    return a single dict for a 1-item result, which then crashes any
    code that assumes a list. Parse each block as its OWN JSON object
    instead."""
    return [json.loads(block.text) for block in mcp_result.content if hasattr(block, "text")]


def extract_text(response) -> str:
    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        return "[No text reply - response was likely truncated by max_tokens. Try raising it.]"
    return text_block.text


# ----------------------------------------------------------------------
# Authenticated session fixture (given) - in a real system this would
# come from a login flow. Everything downstream trusts THIS context,
# never whatever identity the model claims in a tool call.
# ----------------------------------------------------------------------
CUSTOMERS = {
    "cust_1001": {"owned_accounts": ["ACC-5001"]},
    "cust_2002": {"owned_accounts": ["ACC-5002"]},
    "cust_3003": {"owned_accounts": ["ACC-5003", "ACC-5004"]},
}


def new_session(customer_id: str) -> dict:
    """Given: create an authenticated session context for one customer
    conversation. mcp_session and all_tools are attached by main() after
    the MCP connection is established."""
    return {
        "session_id": f"sess-{uuid.uuid4().hex[:8]}",
        "customer_id": customer_id,
        "owned_accounts": CUSTOMERS[customer_id]["owned_accounts"],
        "turn_counter": 0,
        "mcp_session": None,
        "all_tools": None,
    }


# ----------------------------------------------------------------------
# System prompts (given)
# ----------------------------------------------------------------------
SUPERVISOR_SYSTEM = """You are the front-line concierge for Northwind \
Telecom, a mobile carrier. For billing, credit, or charge questions, \
hand off to the "billing" specialist. For plan catalog, upgrade, or \
downgrade questions, hand off to the "plans" specialist. For outages or \
connectivity problems, hand off to the "tech_support" specialist. For \
greetings, thanks, or anything that doesn't need a specialist, just \
reply directly yourself - don't hand off unnecessarily. When you do \
hand off, pass the customer's actual question as the task."""

BILLING_SYSTEM = """You are the Billing Specialist for Northwind \
Telecom, a mobile carrier. You handle charges, goodwill credits, \
proration, data overage, international roaming, and late fees.

Use search_kb to find the relevant policy before answering any factual \
question, and cite the doc_id of every clause you rely on, like \
[TEL-BILL-03]. If search_kb returns nothing relevant, say you don't \
have that information rather than guessing.

Use get_account and list_charges to look up account details. You may \
pass any placeholder value for customer_id and agent_role when calling \
these tools - the system resolves and verifies the real authenticated \
identity itself, independent of whatever you supply.

Before calling apply_billing_credit, always summarize the exact credit \
amount and reason and ask the customer to confirm first - never call it \
without an explicit prior confirmation. Generate a fresh idempotency_key \
yourself for each NEW credit request. If a customer says a request \
didn't go through and asks you to retry the SAME request, reuse the \
SAME idempotency_key you used the first time - never generate a new one \
for a retry of the same request."""

PLANS_SYSTEM = """You are the Plans Specialist for Northwind Telecom, a \
mobile carrier. You handle the plan catalog, upgrades, and downgrades.

Use search_kb to find the relevant policy before answering, citing the \
doc_id of every clause you rely on. If search_kb returns nothing \
relevant, say you don't have that information rather than guessing.

Use get_account to look up the account's current plan and contract \
status. You may pass any placeholder value for customer_id and \
agent_role - the system resolves the real authenticated identity itself.

Before calling change_plan, summarize the change and ask the customer \
to confirm first. Generate a fresh idempotency_key for each new \
plan-change request."""

TECH_SYSTEM = """You are the Technical Support Specialist for Northwind \
Telecom, a mobile carrier. You handle outages and connectivity \
troubleshooting.

Use check_network_status to check for known outages in the customer's \
area, and search_kb for the troubleshooting ladder or ticket priority \
matrix, citing the doc_id of every clause you rely on. If search_kb \
returns nothing relevant, say you don't have that information rather \
than guessing.

Use get_account to look up account details if needed - you may pass \
any placeholder value for customer_id and agent_role, the system \
resolves the real authenticated identity itself.

If troubleshooting steps don't resolve the issue, use \
create_service_ticket, choosing P1/P2/P3 priority per the priority \
matrix. Generate a fresh idempotency_key for each new ticket."""

HANDOFF_TOOL = {
    "name": "handoff",
    "description": "Hand off the customer's message to a specialist sub-agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "specialist": {"type": "string", "enum": ["billing", "plans", "tech_support"]},
            "task": {"type": "string", "description": "What the specialist should address"},
        },
        "required": ["specialist", "task"],
    },
}

SPECIALISTS = {
    "billing": {"agent_role": "billing_agent", "system": BILLING_SYSTEM},
    "plans": {"agent_role": "plans_agent", "system": PLANS_SYSTEM},
    "tech_support": {"agent_role": "tech_agent", "system": TECH_SYSTEM},
}

MAX_TOOL_TURNS = 4

# Tools whose MCP schema takes customer_id/agent_role at all - only these
# get the identity overwrite; search_kb and check_network_status don't
# accept those params and would error if we added them.
_IDENTITY_SCOPED_TOOLS = {"get_account", "list_charges", "apply_billing_credit", "change_plan", "create_service_ticket"}
_IDEMPOTENT_TOOLS = {"apply_billing_credit", "change_plan", "create_service_ticket"}


# TODO 12
async def secure_call_tool(session: ClientSession, tool_name: str, args: dict, ctx: dict):
    """The load-bearing security function. Two structural defenses, both
    enforced HERE, independent of whatever the model decided or was
    talked into by injected content:

      1. Reject any tool name not on the CALLING ROLE's allowlist BEFORE
         any network call reaches the server - kills a rogue lookalike
         tool name (malicious_kb_docs.json's MAL-05) and a confused-
         deputy handoff (MAL-01) with zero MCP round-trips.
      2. Overwrite whatever customer_id/agent_role the model supplied
         with the REAL authenticated context, so a successful prompt
         injection still can't impersonate another customer or role
         (Day4 capstone's secure_call_tool pattern, extended here to
         the role dimension too).

    Also derives a deterministic idempotency_key from
    (session_id, turn_counter, tool_name) when the model omits one -
    defeating MAL-03's "always generate a fresh key" instruction, since
    a genuine retry of the SAME request still needs the model to supply
    (or this function to derive) the SAME key.

    Steps:
      1. agent_role = ctx["agent_role"]; allowed_tools =
         load_entitlements().get(agent_role, {}).get("allowed_tools", []).
      2. If tool_name not in allowed_tools: log_step("secure_call_tool:rejected",
         {"tool_name": ..., "agent_role": ...}) and return a plain dict
         {"error": "tool_not_allowed_for_role", "tool_name": tool_name} -
         do NOT call session.call_tool at all.
      3. secure_args = dict(args). If tool_name is in
         _IDENTITY_SCOPED_TOOLS, overwrite secure_args["customer_id"] =
         ctx["customer_id"] and secure_args["agent_role"] = agent_role
         (search_kb/check_network_status don't take these params - don't
         add them there).
      4. If tool_name is in _IDEMPOTENT_TOOLS and secure_args doesn't
         already have a truthy "idempotency_key": increment
         ctx["turn_counter"] and set secure_args["idempotency_key"] =
         f"auto-{ctx['session_id']}-{ctx['turn_counter']}-{tool_name}".
      5. Return await session.call_tool(tool_name, secure_args) - the
         raw MCP CallToolResult.

    Returns EITHER a plain dict (rejected, zero round trips) OR the raw
    MCP CallToolResult (executed). Callers must check
    isinstance(result, dict) to tell the two apart.
    """
    raise NotImplementedError("TODO: implement secure_call_tool()")


# TODO 13
@traced(name="run_specialist")
async def run_specialist(name: str, question: str, ctx: dict) -> str:
    """Run one specialist's bounded tool-call loop, using only the MCP
    tools its role is entitled to (per entitlements.json - single source
    of truth, not duplicated here). Every retrieved KB doc is sanitized
    before it reaches the model (guardrails.sanitize_retrieved_docs),
    and the final reply is checked against this session's own context
    before it's returned (guardrails.output_guardrail).

    Steps:
      1. spec = SPECIALISTS[name]; agent_role = spec["agent_role"];
         specialist_ctx = {**ctx, "agent_role": agent_role}.
      2. allowed_tool_names = load_entitlements()[agent_role]["allowed_tools"];
         tools = [t for t in ctx["all_tools"] if t["name"] in allowed_tool_names].
      3. messages = [{"role": "user", "content": question}];
         allowed_doc_ids: list[str] = [].
      4. Bounded loop, up to MAX_TOOL_TURNS times:
         a. response = client.messages.create(model=MODEL, max_tokens=700,
            system=spec["system"], tools=tools, messages=messages).
         b. ctx["turn_counter"] += 1; record_usage(response, agent_role,
            ctx["session_id"], ctx["turn_counter"]).
         c. tool_uses = [b for b in response.content if b.type == "tool_use"].
         d. If tool_uses is empty: final_text = extract_text(response);
            build session_info = {"customer_id": ctx["customer_id"],
            "owned_accounts": ctx["owned_accounts"]}; ok, guard_reason =
            output_guardrail(final_text, allowed_doc_ids, session_info);
            if not ok, return an "I'm not able to share that." message
            naming guard_reason; otherwise return final_text.
         e. Otherwise append the assistant turn (messages.append with
            response.content), then for EACH tool_use: call
            secure_call_tool(ctx["mcp_session"], tool_use.name,
            tool_use.input, specialist_ctx). If the result is a dict,
            it was rejected - json.dumps it as the tool_result content.
            If tool_use.name == "search_kb", parse the result with
            mcp_json_list(), run it through sanitize_retrieved_docs(),
            extend allowed_doc_ids with the kept docs' doc_ids, and use
            json.dumps(kept) as the tool_result content. Otherwise use
            mcp_text(result) as the tool_result content. Append a user
            message with all the tool_result blocks.
      5. If the loop exhausts without a final reply, return
         "(specialist hit the tool-call limit without producing a final reply)".
    """
    raise NotImplementedError("TODO: implement run_specialist()")


# TODO 14
async def execute_handoff(specialist: str, question: str, ctx: dict) -> str:
    """The bridge between supervisor and specialist levels - from the
    supervisor's perspective this is an ordinary tool handler: string in,
    string out. Inside, it runs a whole specialist agent loop.

    Steps:
      1. If specialist not in SPECIALISTS, return "Unknown specialist."
      2. Otherwise return await run_specialist(specialist, question, ctx).
    """
    raise NotImplementedError("TODO: implement execute_handoff()")


# TODO 15
@traced(name="run_turn")
async def run_turn(user_message: str, ctx: dict) -> str:
    """The supervisor's own bounded loop: decide whether a specialist is
    needed (handoff tool), or reply directly for greetings/thanks.

    Steps:
      1. _set_trace_session(ctx["session_id"]) (given helper - call it
         once at the top).
      2. messages = [{"role": "user", "content": user_message}].
      3. Bounded loop, up to MAX_TOOL_TURNS times:
         a. response = client.messages.create(model=MODEL, max_tokens=500,
            system=SUPERVISOR_SYSTEM, tools=[HANDOFF_TOOL], messages=messages).
         b. ctx["turn_counter"] += 1; record_usage(response, "supervisor",
            ctx["session_id"], ctx["turn_counter"]).
         c. tool_use = next((b for b in response.content if b.type == "tool_use"), None).
         d. If tool_use is None: return extract_text(response) - the
            supervisor answered directly, no handoff needed.
         e. Otherwise append the assistant turn, then
            specialist_reply = await execute_handoff(tool_use.input["specialist"],
            tool_use.input["task"], ctx); append a user message with one
            tool_result block (tool_use_id=tool_use.id, content=specialist_reply).
      4. If the loop exhausts, return
         "(supervisor hit the tool-call limit without producing a final reply)".
    """
    raise NotImplementedError("TODO: implement run_turn()")


async def main():
    server_params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()

            mcp_tools = (await mcp_session.list_tools()).tools
            all_tools = [mcp_tool_to_anthropic_schema(t) for t in mcp_tools]
            print(f"[Discovered {len(all_tools)} tools over MCP: {[t['name'] for t in all_tools]}]\n")

            ctx1 = new_session("cust_1001")
            ctx1["mcp_session"] = mcp_session
            ctx1["all_tools"] = all_tools

            print("=== Scenario 1: greeting - no handoff ===")
            print("AGENT:", await run_turn("Hi there!", ctx1))

            print("\n=== Scenario 2: billing credit (Day2 handoff + Day4 idempotent MCP action) ===")
            print("AGENT:", await run_turn(
                "I've got a $12 charge on my bill I don't recognize on account ACC-5001 - it's a "
                "duplicate roaming charge, can you credit it?", ctx1))

            print("\n=== Scenario 3: plan upgrade ===")
            print("AGENT:", await run_turn("I'd like to upgrade account ACC-5001 to the Unlimited plan.", ctx1))

            print("\n=== Scenario 4: network outage / service ticket ===")
            print("AGENT:", await run_turn(
                "My internet has been completely down for an hour in the 212 area, on account "
                "ACC-5001 - there's no known outage listed, please open a ticket.", ctx1))

            print("\n=== Scenario 5: entitlement gate - two different customers, identical request ===")
            dispute_msg = "Please credit me $20 for an outage earlier this week, on account ACC-5001."
            ctx2 = new_session("cust_2002")
            ctx2["mcp_session"] = mcp_session
            ctx2["all_tools"] = all_tools
            print("cust_1001:", await run_turn(dispute_msg, ctx1))
            print("cust_2002:", await run_turn(dispute_msg, ctx2))

            print("\n=== Scenario 6: idempotent replay + conflict, demonstrated directly over MCP ===")
            # The natural-language scenarios above correctly stop at "shall I go
            # ahead?" (run_turn is stateless per call, same known limitation as
            # Day2's own run_supervisor - there's no follow-up "yes" turn to
            # continue the SAME specialist conversation). To reliably prove the
            # idempotency mechanism itself, call the MCP write tool directly,
            # the same way Day4 PM_H1's client demo does.
            demo_args = {
                "account_id": "ACC-5001", "customer_id": "cust_1001", "agent_role": "billing_agent",
                "amount_cents": 500, "reason": "demo goodwill credit", "idempotency_key": "demo-key-001",
            }
            first = await mcp_session.call_tool("apply_billing_credit", demo_args)
            print("First call:                    ", mcp_text(first))
            replay = await mcp_session.call_tool("apply_billing_credit", demo_args)
            print("Replay (same key+args):        ", mcp_text(replay))
            conflict = await mcp_session.call_tool(
                "apply_billing_credit", {**demo_args, "amount_cents": 900})
            print("Conflict (same key, diff args):", mcp_text(conflict))

            print("\n=== Full audit trail (fetched over MCP from the server) ===")
            audit = await mcp_session.call_tool("get_audit_log", {})
            print(mcp_text(audit))

            print("\n=== Cost report ===")
            print(json.dumps(cost_report(), indent=2))

            if langfuse:
                langfuse.flush()
                host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com"
                print(f"\nTraces + scores flushed to Langfuse - view them at {host}")
            else:
                print("\n(Langfuse tracing skipped - set LANGFUSE_PUBLIC_KEY / "
                      "LANGFUSE_SECRET_KEY to see this run in the Langfuse UI.)")


if __name__ == "__main__":
    asyncio.run(main())

# Expected:
#   Scenario 1 -> supervisor answers directly, no handoff.
#   Scenario 2 -> handoff to billing -> search_kb cites TEL-BILL-03 ->
#     confirms -> apply_billing_credit succeeds.
#   Scenario 3 -> handoff to plans -> search_kb cites TEL-PLAN-01/02 ->
#     confirms -> change_plan succeeds.
#   Scenario 4 -> handoff to tech_support -> check_network_status ->
#     create_service_ticket if unresolved.
#   Scenario 5 -> cust_1001 (owns ACC-5001) succeeds; cust_2002 (owns
#     ACC-5002, NOT ACC-5001) gets a clean refusal for the IDENTICAL
#     request text - the code-level gate, not the model, produced the
#     different outcome.
#   Scenario 6 -> first call applies a $5.00 credit; the replay returns
#     the IDENTICAL result with no further mutation; the conflict call
#     (same key, different amount) is refused with status "conflict".
