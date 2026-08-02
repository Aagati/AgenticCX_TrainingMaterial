# -*- coding: utf-8 -*-
"""
BONUS TIER C - Alt-Stack Reimplementation: Claude Agent SDK (native)

There is NO solution file for this part. This is the SDK the Day2/Day4
AppliedLabs notebooks use natively (AgentDefinition for sub-agent
dispatch, can_use_tool for permissions, PreToolUse hooks for injection
defense, mcp_servers for MCP) - the primitives here map almost 1:1 onto
this capstone's 7 required topics, which is exactly why it's the bonus
tier and not the required core: candidates never hands-on-practiced this
SDK, only saw it instructor-led.

Every symbol and signature below was verified against the ACTUALLY
INSTALLED claude-agent-sdk==0.2.123 (inspect.signature() /
__annotations__, not recalled from memory) - if a future SDK version
changes a shape, trust `python -c "import claude_agent_sdk as s; help(s.X)"`
over this file's comments.

THE CONSTRAINT: this must talk to the SAME unmodified starter/mcp_server.py
(via mcp_servers' stdio config below, not create_sdk_mcp_server, which is
for wrapping in-process Python functions - our tools already live in a
real separate MCP server process) and reuse starter/permissions.py's
check_permission() UNCHANGED inside can_use_tool - see the discussion
question this is actually testing, at the bottom of this file.

Setup:
    pip install claude-agent-sdk   (already pinned in the repo root)
    Uses the same ANTHROPIC_API_KEY already in .env.
"""

import asyncio
import sys
from pathlib import Path

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    query,
)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_STARTER_DIR = Path(__file__).resolve().parent.parent / "starter"
if _STARTER_DIR.exists() and str(_STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(_STARTER_DIR))

# Reuse Part 2/5 UNCHANGED - the whole point of this exercise.
from permissions import check_permission  # noqa: E402
from guardrails import layer_detect_instruction_injection  # noqa: E402

SERVER_SCRIPT = _STARTER_DIR / "mcp_server.py"

# TODO: a real deployment resolves this from an authenticated session,
# same as agent_team.new_session() - hardcoded here to keep the scaffold
# runnable standalone.
CURRENT_CUSTOMER_ID = "cust_1001"

# Maps the SDK's sub-agent identifier back to our own agent_role naming
# (entitlements.json keys) - the SDK doesn't know about our roles, so
# this translation has to live somewhere.
AGENT_ID_TO_ROLE = {"billing": "billing_agent", "plans": "plans_agent", "tech_support": "tech_agent"}


async def can_use_tool(tool_name: str, tool_input: dict, context) -> PermissionResultAllow | PermissionResultDeny:
    """The native equivalent of agent_team.secure_call_tool()'s role-gate
    half - wired as the SDK's own permission hook instead of a hand-
    written wrapper function. Note what this does NOT reimplement: the
    actual two-dimensional check (ownership + role capability + amount
    limit) is permissions.check_permission(), called here UNCHANGED.
    can_use_tool is a new WIRING POINT for that logic, not a replacement
    for having the logic in the first place - see the discussion
    question at the bottom of this file.

    context.agent_id identifies which sub-agent (billing/plans/
    tech_support) is making this call - see AGENT_ID_TO_ROLE above.
    """
    agent_role = AGENT_ID_TO_ROLE.get(context.agent_id, context.agent_id)
    account_id = tool_input.get("account_id")

    if account_id is None:
        # search_kb / check_network_status take no account_id - nothing
        # to gate on ownership; every role may call them.
        return PermissionResultAllow()

    allowed, reason = check_permission(
        CURRENT_CUSTOMER_ID, account_id, agent_role, tool_name,
        amount_cents=tool_input.get("amount_cents"),
    )
    if allowed:
        return PermissionResultAllow()
    return PermissionResultDeny(message=reason)


async def block_instruction_injection(input_data, tool_use_id, hook_context):
    """A native PreToolUse hook doing the SAME check as guardrails.py's
    layer_detect_instruction_injection(), but wired at the point where
    the SDK is ABOUT to execute a tool rather than scanning retrieved
    text before it reaches the model. Compare this wiring point to
    guardrails.sanitize_retrieved_docs() (Part 5) - same detection logic,
    different place in the pipeline; discuss which placement you'd
    actually want and why they're not redundant with each other.
    """
    tool_input_text = " ".join(str(v) for v in input_data["tool_input"].values())
    result = layer_detect_instruction_injection(tool_input_text)
    if result["flagged"]:
        return {"decision": "block", "reason": f"blocked by PreToolUse hook: {result['reason']}"}
    return {}


BILLING_AGENT = AgentDefinition(
    description="Handles charges, goodwill credits, proration, overage, roaming, late fees.",
    prompt=(
        "You are the Billing Specialist for Northwind Telecom. Use search_kb "
        "before answering factual questions, citing doc_ids. Confirm with the "
        "customer before calling apply_billing_credit."
    ),
    tools=["mcp__northwind__search_kb", "mcp__northwind__get_account",
           "mcp__northwind__list_charges", "mcp__northwind__apply_billing_credit"],
    mcpServers=["northwind"],
)
PLANS_AGENT = AgentDefinition(
    description="Handles the plan catalog, upgrades, and downgrades.",
    prompt=(
        "You are the Plans Specialist for Northwind Telecom. Use search_kb "
        "before answering, citing doc_ids. Confirm with the customer before "
        "calling change_plan."
    ),
    tools=["mcp__northwind__search_kb", "mcp__northwind__get_account", "mcp__northwind__change_plan"],
    mcpServers=["northwind"],
)
TECH_AGENT = AgentDefinition(
    description="Handles outages and connectivity troubleshooting.",
    prompt=(
        "You are the Technical Support Specialist for Northwind Telecom. Use "
        "check_network_status and search_kb before answering. Use "
        "create_service_ticket if troubleshooting doesn't resolve the issue."
    ),
    tools=["mcp__northwind__search_kb", "mcp__northwind__check_network_status",
           "mcp__northwind__get_account", "mcp__northwind__create_service_ticket"],
    mcpServers=["northwind"],
)

# TODO: exact tool-name-prefix convention (mcp__<server>__<tool>) should
# be confirmed against your installed SDK version's MCP naming scheme
# before relying on the `tools=[...]` allowlists above - print
# `(await options-derived client).mcp_server_info` or similar at runtime
# to see the actual discovered names if AgentDefinition's tools filter
# doesn't seem to be taking effect.

OPTIONS = ClaudeAgentOptions(
    model="claude-sonnet-5",
    system_prompt=(
        "You are the front-line concierge for Northwind Telecom. Delegate "
        "billing questions to the billing sub-agent, plan questions to the "
        "plans sub-agent, and connectivity questions to the tech_support "
        "sub-agent. Reply directly for greetings."
    ),
    mcp_servers={
        "northwind": {"type": "stdio", "command": sys.executable, "args": [str(SERVER_SCRIPT)]},
    },
    agents={"billing": BILLING_AGENT, "plans": PLANS_AGENT, "tech_support": TECH_AGENT},
    can_use_tool=can_use_tool,
    hooks={"PreToolUse": [HookMatcher(hooks=[block_instruction_injection])]},
)


async def main():
    prompt = (
        "I've got a $12 charge on my bill I don't recognize on account "
        "ACC-5001 - it's a duplicate roaming charge, can you credit it?"
    )
    print(f"CUSTOMER: {prompt}\n")
    async for message in query(prompt=prompt, options=OPTIONS):
        # TODO: inspect `message` (AssistantMessage/ResultMessage/etc. -
        # see claude_agent_sdk.types) and print/collect the parts you
        # care about. Left minimal here since the interesting part of
        # this exercise is the OPTIONS wiring above, not message parsing.
        print(type(message).__name__, message)


if __name__ == "__main__":
    asyncio.run(main())

# Discussion questions (bring back to the group, per bonus/README.md):
#   - can_use_tool() above calls permissions.check_permission() UNCHANGED.
#     Did the Agent SDK make any part of Part 2 redundant, or did it just
#     give the SAME logic a different place to live? Be specific about
#     what, if anything, you deleted from agent_team.secure_call_tool()
#     versus what you just moved.
#   - The PreToolUse hook and Part 5's sanitize_retrieved_docs() run the
#     exact same detection function at two different points in the
#     pipeline (tool-execution-time vs. retrieval-time). Is one strictly
#     better, or do they catch genuinely different things?
#   - AgentDefinition's `tools` field is an ALLOWLIST enforced by the SDK
#     itself - a capability reduction, not a runtime check. Compare this
#     to secure_call_tool()'s allowlist check in agent_team.py: one is
#     structural (the tool literally isn't offered to the model), the
#     other is enforced in your own code after the model already tried.
#     Which would you trust more under prompt injection, and why?
#   - This file is a starting point, not a finished reimplementation -
#     the CanUseToolShadowedWarning the SDK can raise (a tool present in
#     `tools`/`AgentDefinition.tools` silently shadows `can_use_tool`
#     entirely) is a real, documented gotcha worth deliberately
#     triggering once, so you know what it looks like before it bites
#     you in a real deployment.
