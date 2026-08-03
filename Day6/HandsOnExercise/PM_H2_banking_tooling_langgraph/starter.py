"""
PM · H2 — Banking: Tooling & Actions via LangGraph (STARTER)

Build ONE graph shape and run it twice — once with a real Claude node,
once with a Gemini node (real if GEMINI_API_KEY/GOOGLE_API_KEY is set, a
duck-typed simulated model otherwise) — to make "Gemini vs. the modular
stack" concrete: the model is a swappable node, the graph doesn't change.
Scenario: banking customer checks balance (safe, read-only) and reports
a lost card (irreversible — freeze it only after they confirm).

Two more production concerns on top of the vendor-swap point:
  - COST TIERING (build_tiered_graph) — the same graph shape again, but
    the agent node decides with a cheap model and the execute node only
    pays for a capable model on the path that touches freeze_card.
  - HARDENED TOOL EXECUTION (_run_tool_call, freeze_card's idempotency
    check, both given below) — an unknown tool name or a raised exception
    degrades to a safe reply instead of crashing the graph, and freezing
    an already-frozen card is a no-op, not a second "success."
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CLAUDE_MODEL = "claude-sonnet-5"
CLAUDE_CHEAP_MODEL = "claude-haiku-4-5-20251001"
GEMINI_MODEL = "gemini-flash-latest"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "account_ledger.json") as f:
    ACCOUNT = json.load(f)

SYSTEM_PROMPT = (
    "You are a banking support agent. Use get_account_info for balance or "
    "deposit questions, and freeze_card when the caller reports their card "
    "lost or stolen. Reply in short, plain sentences."
)


@tool
def get_account_info() -> dict:
    """Look up the caller's current balance, card status, and most recent paycheck deposit."""
    return {k: v for k, v in ACCOUNT.items() if k != "customer_id"}


@tool
def freeze_card() -> dict:
    """Freeze the caller's card immediately — use this when they report it lost or stolen."""
    if ACCOUNT["card_status"] == "frozen":
        # Given — idempotency guard: a retried or double-invoked freeze
        # must not read as a fresh action — same request twice, same
        # safe result.
        return {"card_status": "frozen", "confirmation": "Card was already frozen — no action taken."}
    ACCOUNT["card_status"] = "frozen"
    return {"card_status": ACCOUNT["card_status"], "confirmation": "Card frozen successfully."}


TOOLS = [get_account_info, freeze_card]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def _run_tool_call(call: dict) -> tuple[dict | None, str | None]:
    """Given — executes a tool call safely: (result, None) on success, or
    (None, message) if the model asked for a tool that doesn't exist or
    the tool itself raised. Both execute nodes route through this so the
    hardening lives in one place instead of being duplicated per node."""
    if call["name"] not in TOOLS_BY_NAME:
        return None, f"Sorry, I can't do that ({call['name']} isn't a tool I have)."
    try:
        return TOOLS_BY_NAME[call["name"]].invoke(call.get("args", {})), None
    except Exception as exc:
        return None, f"Sorry, that action failed: {exc}"


@dataclass
class SimResponse:
    """Duck-types the piece of an AIMessage our nodes actually read."""
    content: str
    tool_calls: list = field(default_factory=list)


class SimulatedGeminiModel:
    """Given — same .invoke(messages) -> object-with-.content/.tool_calls
    interface a real LangChain chat model exposes, used only when no
    Gemini key is set."""

    def invoke(self, messages):
        last = messages[-1]
        if isinstance(last, ToolMessage):
            data = json.loads(last.content)
            if "confirmation" in data:
                # freeze_card's result — the only one with a "confirmation" key.
                # (get_account_info's result ALSO has "card_status" in it, so
                # branching on that key alone would misroute every call here.)
                return SimResponse(content=f"(simulated) Your card is now {data['card_status']}.")
            return SimResponse(
                content=f"(simulated) Your balance is ${data.get('balance')}, "
                f"last deposit landed {data.get('last_paycheck_deposit')}."
            )
        text = last.content.lower()
        if "balance" in text or "deposit" in text:
            return SimResponse(content="", tool_calls=[{"name": "get_account_info", "args": {}, "id": "sim-1"}])
        if any(w in text for w in ("lost", "stolen", "freeze")):
            return SimResponse(content="", tool_calls=[{"name": "freeze_card", "args": {}, "id": "sim-2"}])
        return SimResponse(content="(simulated) I can help with balance, deposit, or card questions.")


class ActionState(TypedDict):
    message: str
    confirmed: bool
    reply: str
    _pending_call: dict | None
    _ai_content: str


def make_agent_node(llm_with_tools):
    """
    TODO 1: Return a node function agent_node(state) that:
      - builds messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(state["message"])]
      - calls llm_with_tools.invoke(messages)
      - if response.tool_calls is empty, returns {"reply": response.content,
        "_pending_call": None} (no action needed)
      - otherwise takes tool_calls[0] as `call`. If call["name"] ==
        "freeze_card" AND state.get("confirmed") is falsy, return a dict
        with "reply" set to a confirmation-request message, "_pending_call":
        call, and "_ai_content": response.content — DO NOT execute yet.
      - otherwise (get_account_info, or freeze_card already confirmed),
        return {"_pending_call": call, "_ai_content": response.content}
        with no "reply" key — execution happens in the execute node.
    """
    def agent_node(state: ActionState) -> dict:
        messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(state["message"])]
        response = llm_with_tools.invoke(messages)

        if not response.tool_calls:
            return {"reply": response.content, "_pending_call": None}

        call = response.tool_calls[0]
        if call["name"] == "freeze_card" and not state.get("confirmed"):
            return {
                "reply": "This will freeze your card immediately — reply 'yes' to confirm.",
                "_pending_call": call,
                "_ai_content": response.content,
            }
        return {"_pending_call": call, "_ai_content": response.content}

    return agent_node


def make_execute_node(llm_with_tools):
    """
    TODO 2: Return a node function execute_node(state) that:
      - pulls call = state["_pending_call"], calls result, error =
        _run_tool_call(call) — this given helper already handles an
        unknown tool name or a raised exception, so you don't re-check
        those here
      - if error, return {"reply": error, "_pending_call": None}
        immediately (skip the model call — there's nothing to follow up)
      - otherwise, rebuilds the full message history: SystemMessage,
        HumanMessage (original), AIMessage(content=state.get("_ai_content")
        or "", tool_calls=[call]), ToolMessage(content=json.dumps(result),
        tool_call_id=call["id"])
      - calls llm_with_tools.invoke(messages) again for the natural-language
        follow-up
      - returns {"reply": follow_up.content, "_pending_call": None}
    """
    def execute_node(state: ActionState) -> dict:
        call = state["_pending_call"]
        result, error = _run_tool_call(call)
        if error:
            return {"reply": error, "_pending_call": None}
        messages = [
            SystemMessage(SYSTEM_PROMPT),
            HumanMessage(state["message"]),
            AIMessage(content=state.get("_ai_content") or "", tool_calls=[call]),
            ToolMessage(content=json.dumps(result), tool_call_id=call["id"]),
        ]
        follow_up = llm_with_tools.invoke(messages)
        return {"reply": follow_up.content, "_pending_call": None}

    return execute_node


def make_tiered_execute_node(cheap_llm_with_tools, capable_llm_with_tools):
    """
    TODO 5: Cost-tiered execute node — same shape as make_execute_node's
    execute_node, but before the follow-up call, pick which model answers
    it: llm_with_tools = capable_llm_with_tools if call["name"] ==
    "freeze_card" else cheap_llm_with_tools. Tool execution itself
    (_run_tool_call) is identical either way — only the follow-up model
    differs.
    """
    def execute_node(state: ActionState) -> dict:
        call = state["_pending_call"]
        result, error = _run_tool_call(call)
        if error:
            return {"reply": error, "_pending_call": None}
        llm_with_tools = capable_llm_with_tools if call["name"] == "freeze_card" else cheap_llm_with_tools
        messages = [
            SystemMessage(SYSTEM_PROMPT),
            HumanMessage(state["message"]),
            AIMessage(content=state.get("_ai_content") or "", tool_calls=[call]),
            ToolMessage(content=json.dumps(result), tool_call_id=call["id"]),
        ]
        follow_up = llm_with_tools.invoke(messages)
        return {"reply": follow_up.content, "_pending_call": None}

    return execute_node


def route_after_agent(state: ActionState) -> Literal["execute", "end"]:
    """
    TODO 3: If state["_pending_call"] is None, return "end". If it's a
    freeze_card call and state.get("confirmed") is falsy, ALSO return "end"
    (the confirmation prompt is already the reply — the gate holds).
    Otherwise return "execute".
    """
    call = state.get("_pending_call")
    if call is None:
        return "end"
    if call["name"] == "freeze_card" and not state.get("confirmed"):
        return "end"
    return "execute"


def build_action_graph(llm_with_tools):
    """
    TODO 4: Wire the StateGraph(ActionState): add_node("agent",
    make_agent_node(llm_with_tools)), add_node("execute",
    make_execute_node(llm_with_tools)), set_entry_point("agent"),
    add_conditional_edges("agent", route_after_agent, {"execute": "execute",
    "end": END}), add_edge("execute", END). Return builder.compile().
    """
    builder = StateGraph(ActionState)
    builder.add_node("agent", make_agent_node(llm_with_tools))
    builder.add_node("execute", make_execute_node(llm_with_tools))
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", route_after_agent, {"execute": "execute", "end": END})
    builder.add_edge("execute", END)
    return builder.compile()


def build_tiered_graph(cheap_llm_with_tools, capable_llm_with_tools):
    """
    TODO 6: Same wiring as build_action_graph, but: add_node("agent",
    make_agent_node(cheap_llm_with_tools)) — deciding which tool to call
    is a cheap classification task, no need for the capable model there —
    and add_node("execute", make_tiered_execute_node(cheap_llm_with_tools,
    capable_llm_with_tools)). Same entry point, conditional edges, and
    final edge as build_action_graph.
    """
    builder = StateGraph(ActionState)
    builder.add_node("agent", make_agent_node(cheap_llm_with_tools))
    builder.add_node("execute", make_tiered_execute_node(cheap_llm_with_tools, capable_llm_with_tools))
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", route_after_agent, {"execute": "execute", "end": END})
    builder.add_edge("execute", END)
    return builder.compile()


claude_llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=200).bind_tools(TOOLS)
claude_cheap_llm = ChatAnthropic(model=CLAUDE_CHEAP_MODEL, max_tokens=200).bind_tools(TOOLS)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _vertex_client import get_gemini_chat_model

gemini_llm = get_gemini_chat_model(GEMINI_MODEL, tools=TOOLS) or SimulatedGeminiModel()
_gemini_key = not isinstance(gemini_llm, SimulatedGeminiModel)

claude_graph = build_action_graph(claude_llm)
gemini_graph = build_action_graph(gemini_llm)
tiered_graph = build_tiered_graph(claude_cheap_llm, claude_llm)


def demo(label: str, graph):
    print(f"\n=== {label} ===")

    print("Customer: What's my account balance?")
    result = graph.invoke({"message": "What's my account balance?", "confirmed": False})
    print(f"Agent: {result['reply']}")

    print("\nCustomer: I lost my card, please freeze it.")
    pending = graph.invoke({"message": "I lost my card, please freeze it.", "confirmed": False})
    print(f"Agent: {pending['reply']}")
    print(f"[card_status after request, NOT yet confirmed: {ACCOUNT['card_status']}]")

    print("\nCustomer: Yes, freeze it.")
    confirmed = graph.invoke({"message": "I lost my card, please freeze it.", "confirmed": True})
    print(f"Agent: {confirmed['reply']}")
    print(f"[card_status after confirmation: {ACCOUNT['card_status']}]")


if __name__ == "__main__":
    demo("Claude node (real)", claude_graph)
    ACCOUNT["card_status"] = "active"  # reset the shared fixture between demos
    demo(f"Gemini node ({'real' if _gemini_key else 'simulated'})", gemini_graph)
    ACCOUNT["card_status"] = "active"
    demo("Cost-tiered (haiku decides + reads, sonnet executes freeze_card)", tiered_graph)

    print("\n=== Idempotency check — freezing an already-frozen card ===")
    repeat = claude_graph.invoke({"message": "I lost my card, please freeze it.", "confirmed": True})
    print(f"Agent: {repeat['reply']}")
    print(f"[card_status still: {ACCOUNT['card_status']}]")
