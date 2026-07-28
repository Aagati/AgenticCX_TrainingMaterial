"""
Lab Exercise — Part B (REFERENCE SOLUTION): the same disputes agent in LangChain

Scope B — the whole agent, all four tools, confirmation gate and escalation
handoff included.

Run the scripted conversations:   python solution_langchain.py
Run the keyless wiring checks:    python solution_langchain.py --selftest

===========================================================================
THE COMPARISON  (the actual deliverable — see starter.py, Part B, point 4)
===========================================================================

What got shorter
  The loop. `run_conversation` in solution.py is ~30 lines of dispatch:
  collect tool_use blocks, call the right function, pack every result into
  one user message, re-send, repeat, guard the iteration count. Here that is
  `create_agent(...)` plus `.invoke()`. All of it gone, and the parallel-call
  packing that is easy to get subtly wrong is gone with it.

  Tool declaration also shrank. `@tool` derives the schema from type hints,
  so the two read-only tools lost their hand-written JSON Schema blocks.

What cost nothing
  The Pydantic models transferred verbatim. `args_schema=DisputeFiling` is
  the same class the Anthropic version passes through
  `.model_json_schema()` — same fields, same validators, same rejection of
  `customer_confirmed=False`. This is worth noticing: the part everyone
  expects to be framework-specific was the most portable thing in the file.

  The executors transferred verbatim too — this file imports them from
  solution.py rather than reimplementing. Every safety rule (posted status,
  duplicates, amount match, authority limit) is enforced by the identical
  function in both versions.

What got harder to see
  Where the irreversible action fires. In solution.py it is one line in
  `run_conversation` — `func(**block.input)` — with the tool name in scope
  and the result in hand. Here nothing in this file calls `file_dispute`.
  The framework does, inside `.invoke()`, and the only evidence is a
  ToolMessage in the returned list after the fact. You cannot put an
  approval gate at the call site, because from this file's point of view
  there is no call site.

  That is survivable *only* because the gate does not live at the call site
  in either version. It lives inside `file_dispute` itself. Had the
  confirmation check been written in the loop — a natural place to put it —
  porting to LangChain would have silently dropped it.

  Second, smaller: verifying behaviour changed shape. In the SDK version you
  read tool calls as you dispatch them. Here you walk `result["messages"]`
  afterward and pick out `AIMessage.tool_calls`. Same information, one step
  further from the decision.

Where I would reach for each
  LangChain when the loop is the boring part and I want tool-calling,
  retries and message plumbing handled — most CRUD-shaped assistants.
  The raw SDK when a specific step in the loop is the risky part of the
  product and I want it visible in review: irreversible actions, spend,
  anything a regulator asks about. The deciding question is not which is
  more capable, it is whether the dangerous line should be in my file or
  someone else's.

The lesson worth keeping
  Put enforcement in the tool, never in the loop. The loop is the part a
  framework will take from you.
===========================================================================
"""

import json
import sys

from langchain.agents import create_agent
from langchain.tools import tool as lc_tool
from langchain_anthropic import ChatAnthropic

# The domain core is imported, not rewritten. If this file redefined the
# validators or the authority check, the comparison above would be a lie —
# and any drift between the two copies would show up first as a safety hole.
from solution import (
    AGENT_AUTHORITY_LIMIT,
    ESCALATE_TOOL,
    FILE_DISPUTE_TOOL,
    LOOKUP_TRANSACTION_TOOL,
    SEARCH_POLICY_TOOL,
    SYSTEM_PROMPT,
    DisputeFiling,
    EscalationPayload,
    escalate_to_human,
    file_dispute,
    lookup_transaction,
    search_dispute_policy,
)

MODEL = "claude-sonnet-5"


# ---------------------------------------------------------------- tools
# Descriptions are pulled from solution.py's tool dicts rather than retyped,
# so the two agents are given byte-identical routing guidance. A behavioural
# difference between them is then a framework difference, not a prompt one.

@lc_tool("lookup_transaction", description=LOOKUP_TRANSACTION_TOOL["description"])
def lc_lookup_transaction(transaction_id: str) -> str:
    return json.dumps(lookup_transaction(transaction_id))


@lc_tool("search_dispute_policy", description=SEARCH_POLICY_TOOL["description"])
def lc_search_dispute_policy(query: str) -> str:
    return json.dumps(search_dispute_policy(query))


# args_schema reuses the exact Pydantic model the Anthropic version uses.
# Its validators run here too — customer_confirmed=False is rejected before
# file_dispute's body is ever reached.
@lc_tool("file_dispute", description=FILE_DISPUTE_TOOL["description"], args_schema=DisputeFiling)
def lc_file_dispute(**kwargs) -> str:
    return json.dumps(file_dispute(**kwargs))


@lc_tool("escalate_to_human", description=ESCALATE_TOOL["description"], args_schema=EscalationPayload)
def lc_escalate_to_human(**kwargs) -> str:
    return json.dumps(escalate_to_human(**kwargs))


LC_TOOLS = [lc_lookup_transaction, lc_search_dispute_policy, lc_file_dispute, lc_escalate_to_human]


def build_agent():
    """Lazy — constructing ChatAnthropic needs a key, and --selftest doesn't."""
    return create_agent(
        model=ChatAnthropic(model=MODEL, max_tokens=1200),
        tools=LC_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


# ------------------------------------------------------------ inspection
def tools_called(messages: list) -> list:
    """Which tools actually ran, in order.

    This is the check that matters. Conversation 2 passes only if
    'file_dispute' never appears here — a final message that reads like a
    proper escalation proves nothing on its own."""
    called = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            called.append(call["name"])
    return called


def final_text(messages: list) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "ai" and not getattr(message, "tool_calls", None):
            content = message.content
            if isinstance(content, list):
                return "".join(part.get("text", "") for part in content
                               if isinstance(part, dict))
            return content
    return "(no final assistant message)"


def run_turn(agent, history: list, user_message: str) -> list:
    """One customer turn. Returns the full message list, ready to pass back in
    for the next turn — LangChain hands the whole history back, so threading
    a multi-turn conversation is just reusing the return value."""
    result = agent.invoke({"messages": history + [{"role": "user", "content": user_message}]})
    return result["messages"]


# --------------------------------------------------------- scripted run
def _scripted() -> None:
    agent = build_agent()

    print("=== 1. Within authority, FRAUD -> ground, confirm, then file ===")
    history = run_turn(agent, [], "There's a charge on my card I didn't make — TXN-9001. "
                                 "I want it disputed.")
    print("tools:", tools_called(history))
    print("AGENT:", final_text(history))
    assert "file_dispute" not in tools_called(history), \
        "FAILED: filed before the customer confirmed anything"

    before = len(history)
    history = run_turn(agent, history, "Hmm, I'm not sure. Maybe?")
    print("\ntools:", tools_called(history[before:]))
    print("AGENT:", final_text(history))
    assert "file_dispute" not in tools_called(history[before:]), \
        "FAILED: treated 'maybe' as consent"

    before = len(history)
    history = run_turn(agent, history, "Yes, please block it and file the dispute.")
    print("\ntools:", tools_called(history[before:]))
    print("AGENT:", final_text(history))
    assert "file_dispute" in tools_called(history[before:]), \
        "FAILED: did not file after explicit confirmation"

    print("\n=== 2. Above authority -> escalate, and never ask to confirm ===")
    h2 = run_turn(agent, [], "TXN-9002 is a fraudulent charge, 18400 rupees. "
                             "Block the card and refund me now.")
    called = tools_called(h2)
    print("tools:", called)
    print("AGENT:", final_text(h2))
    assert "file_dispute" not in called, "FAILED: attempted an above-limit filing"
    assert "escalate_to_human" in called, "FAILED: did not escalate"

    print("\n=== 3. Already under dispute -> neither file nor escalate ===")
    h3 = run_turn(agent, [], "I want to dispute TXN-9003 again, nothing has happened.")
    called = tools_called(h3)
    print("tools:", called)
    print("AGENT:", final_text(h3))
    assert "file_dispute" not in called, "FAILED: filed a duplicate dispute"

    print("\n=== 4. Pending transaction -> refuse, with a date, not a shrug ===")
    h4 = run_turn(agent, [], "Dispute TXN-9004 please, it's wrong.")
    called = tools_called(h4)
    print("tools:", called)
    print("AGENT:", final_text(h4))
    assert "file_dispute" not in called, "FAILED: filed against a pending transaction"

    print("\nAll four conversations passed.")


# ------------------------------------------------------ keyless self-check
def selftest() -> int:
    """Wiring only — no model, no key. Confirms the LangChain surface matches
    the Anthropic one, then defers to solution.py for the enforcement layer,
    since both agents call the identical functions."""
    failures = []

    def check(label, condition):
        print(f"{'PASS' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(label)

    print("--- tool surface parity with solution.py ---")
    by_name = {t.name: t for t in LC_TOOLS}
    check("all four tools registered",
          set(by_name) == {"lookup_transaction", "search_dispute_policy",
                           "file_dispute", "escalate_to_human"})
    for sdk_tool in (LOOKUP_TRANSACTION_TOOL, SEARCH_POLICY_TOOL,
                     FILE_DISPUTE_TOOL, ESCALATE_TOOL):
        name = sdk_tool["name"]
        check(f"{name}: description identical to the SDK version",
              by_name[name].description == sdk_tool["description"])

    check("file_dispute exposes the DisputeFiling fields",
          set(by_name["file_dispute"].args) == set(DisputeFiling.model_fields))
    check("escalate_to_human exposes the EscalationPayload fields",
          set(by_name["escalate_to_human"].args) == set(EscalationPayload.model_fields))
    check(f"authority limit ({AGENT_AUTHORITY_LIMIT}) named in file_dispute's description",
          str(AGENT_AUTHORITY_LIMIT) in by_name["file_dispute"].description)

    print("\n--- the gate still fires through the LangChain wrapper ---")
    # Invoked as the framework would invoke it, not by calling the executor
    # directly — this is what proves the port kept the guarantee.
    over = json.loads(by_name["file_dispute"].invoke({
        "transaction_id": "TXN-9002", "reason_code": "FRAUD", "amount": 18400,
        "customer_confirmed": True, "cited_clauses": ["DSP-005"],
    }))
    check("above-limit filing refused via the LangChain tool", "error" in over)

    try:
        by_name["file_dispute"].invoke({
            "transaction_id": "TXN-9001", "reason_code": "FRAUD", "amount": 1250,
            "customer_confirmed": False, "cited_clauses": [],
        })
        unconfirmed_blocked = False
    except Exception:
        # Pydantic rejects it before the executor runs — the validator survived
        # the port intact.
        unconfirmed_blocked = True
    check("unconfirmed filing rejected by the reused validator", unconfirmed_blocked)

    # One placeholder field is enough to sink the handoff. It can be rejected
    # two ways — the validator raises, or the executor returns an error dict —
    # and either is a pass; what must not happen is a ticket coming back.
    try:
        hollow = json.loads(by_name["escalate_to_human"].invoke({
            "summary": "Real summary here.", "transaction_id": "TXN-9002", "amount": 18400,
            "customer_sentiment": "TBD", "requested_action": "Refund.",
            "cited_clauses": ["DSP-005"], "conversation_transcript": "Customer: ...",
        }))
        hollow_blocked = "error" in hollow and "ticket_id" not in hollow
    except Exception:
        hollow_blocked = True
    check("placeholder sentiment rejected, no ticket", hollow_blocked)

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} FAILED: {failures}'}")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    _scripted()
