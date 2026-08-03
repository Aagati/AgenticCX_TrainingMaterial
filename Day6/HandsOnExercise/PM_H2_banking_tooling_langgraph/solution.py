"""
LAB-2 => Banking: Tooling & Actions via LangGraph. 

This lab builds a "tool the model decides to call" shape as a LangGraph
StateGraph with a confirm-gate on the irreversible action (freeze_card) —
a "confirm before an irreversible action" pattern, as an explicit graph
node instead of an if-statement.

The graph itself (build_action_graph) doesn't care which model powers the
"agent" node — it's built once and instantiated TWICE, once with a Claude
node and once with a Gemini node. That's the concrete, code-level answer to
"Gemini vs. the modular stack": in the modular stack, the model is a
swappable node behind a common LangChain interface, not a monolith you
build your whole session around (contrast with a native-audio session,
where the model IS the whole pipeline).

Gemini node is REAL if GEMINI_API_KEY/GOOGLE_API_KEY is set, else a
duck-typed simulated model with the SAME .invoke(messages) interface keeps
the graph runnable either way. The Claude node is always real (every lab
in this repo assumes ANTHROPIC_API_KEY is configured).

Two more production concerns on top of the vendor-swap point:
  - COST TIERING (build_tiered_graph) — the same graph shape again, but
    the agent node decides with a cheap model and the execute node only
    pays for a capable model on the path that touches freeze_card. Not
    every node in a graph needs the same model.
  - HARDENED TOOL EXECUTION (_run_tool_call, freeze_card's idempotency
    check) — an unknown tool name or a raised exception degrades to a
    safe reply instead of crashing the graph, and freezing an
    already-frozen card is a no-op, not a second "success."
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
    "lost or stolen. Only state balance, deposit, or card status from "
    "get_account_info's result — never guess. Reply in short, plain "
    "sentences."
)


@tool
def get_account_info() -> dict:
    """Look up the caller's current balance, card status, and most recent paycheck deposit."""
    return {k: v for k, v in ACCOUNT.items() if k != "customer_id"}


@tool
def freeze_card() -> dict:
    """Freeze the caller's card immediately — use this when they report it lost or stolen."""
    if ACCOUNT["card_status"] == "frozen":
        # Idempotency guard: a retried or double-invoked freeze must not
        # read as a fresh action — same request twice, same safe result.
        return {"card_status": "frozen", "confirmation": "Card was already frozen — no action taken."}
    ACCOUNT["card_status"] = "frozen"
    return {"card_status": ACCOUNT["card_status"], "confirmation": "Card frozen successfully."}


TOOLS = [get_account_info, freeze_card]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def _run_tool_call(call: dict) -> tuple[dict | None, str | None]:
    """Executes a tool call safely: (result, None) on success, or
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
    """Same .invoke(messages) -> object-with-.content/.tool_calls interface
    a real LangChain chat model exposes — used only when no Gemini key is
    set, so build_action_graph() never has to know the difference."""

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
    """Cost-tiered execute node: the read-only tool's follow-up is answered
    by the cheap model, the irreversible tool's follow-up is answered by
    the capable model. Tool execution itself (_run_tool_call) is identical
    either way — only the follow-up model differs."""
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
    call = state.get("_pending_call")
    if call is None:
        return "end"
    if call["name"] == "freeze_card" and not state.get("confirmed"):
        return "end"  # confirmation request is already the reply — stop, don't execute
    return "execute"


def build_action_graph(llm_with_tools):
    """Same 2-node graph shape regardless of which model powers it — swap
    the argument, not the graph."""
    builder = StateGraph(ActionState)
    builder.add_node("agent", make_agent_node(llm_with_tools))
    builder.add_node("execute", make_execute_node(llm_with_tools))
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", route_after_agent, {"execute": "execute", "end": END})
    builder.add_edge("execute", END)
    return builder.compile()


def build_tiered_graph(cheap_llm_with_tools, capable_llm_with_tools):
    """Same graph shape again, but the agent node decides with the CHEAP
    model (deciding which tool to call is a cheap classification task)
    while the execute node picks cheap vs. capable per tool via
    make_tiered_execute_node — the capable model only gets invoked on the
    path that touches an irreversible action."""
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

# Expected: all three graphs behave identically at the STATE-MACHINE level
# regardless of which model is answering — balance question resolves in
# one agent-node pass, freeze_card request STOPS at the agent node with a
# confirmation prompt and card_status stays "active", and only the
# confirmed=True re-invoke reaches the execute node and flips card_status
# to "frozen". Any wording differences across demos come from the model,
# never from the graph shape — that's the point of this lab. The tiered
# demo additionally shows the SAME graph topology answering the balance
# question with the cheap model and the freeze confirmation/follow-up with
# the capable one — check the tool_calls[0]["id"] prefix or just watch
# response latency/style differ between the two tools within one demo.
# The idempotency check re-freezes a card that's already frozen (left over
# from the tiered demo) and should get back "already frozen — no action
# taken" instead of a second "frozen successfully" — the guard in
# freeze_card(), not a state check in the graph.
