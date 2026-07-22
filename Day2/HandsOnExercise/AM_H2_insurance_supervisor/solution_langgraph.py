"""
AM · H2 — Insurance Supervisor Routing (LangGraph VARIANT)

Same routing task as solution.py (classify -> claims specialist OR policy
specialist), reimplemented as an explicit LangGraph StateGraph instead of a
plain if/else in Python. This is the textbook supervisor pattern the
contents.md "Agent build" row calls out LangGraph for: a typed state object,
nodes as functions, and a conditional edge that picks the next node — the
same shape you'd use for a much bigger graph.

Setup:
    pip install langgraph langchain-anthropic
    Uses the same ANTHROPIC_API_KEY already in .env — no new key needed.
"""

import json
import sys
from typing import Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "claude-sonnet-5"
llm = ChatAnthropic(model=MODEL, max_tokens=300)

with open("mock_data.json") as f:
    DATA = json.load(f)


class RoutingState(TypedDict):
    message: str
    intent: str
    specialist: str
    reply: str


def classify_intent_node(state: RoutingState) -> dict:
    response = llm.invoke([
        ("system", "Classify the customer message as exactly one word: either "
                   "'claims' (filing or checking status of a claim) or 'policy' "
                   "(coverage/policy wording questions). Reply with ONLY that one word."),
        ("human", state["message"]),
    ])
    return {"intent": response.content.strip().lower()}


def claims_specialist_node(state: RoutingState) -> dict:
    claims_context = json.dumps(DATA["claims"], indent=2)
    system = f"""You are a Claims Specialist for an insurance company. You are
empathetic and focused on claim status and next steps. Here is the claims
data you have access to:

{claims_context}

If asked a general policy coverage question, say that's outside what you
handle and that you can transfer them to the Policy team."""
    response = llm.invoke([("system", system), ("human", state["message"])])
    return {"specialist": "Claims Specialist", "reply": response.content}


def policy_specialist_node(state: RoutingState) -> dict:
    clauses_context = "\n\n".join(
        f"[{c['id']}] {c['title']}\n{c['text']}" for c in DATA["policy_clauses"]
    )
    system = f"""You are a Policy Specialist for an insurance company. You are
precise and citation-oriented. Answer ONLY using the policy clauses below,
citing the clause id (e.g. [POL-010]) for every factual claim. If the answer
isn't in these clauses, say you don't have that information rather than
guessing. If asked about claim status, say that's outside what you handle.

{clauses_context}"""
    response = llm.invoke([("system", system), ("human", state["message"])])
    return {"specialist": "Policy Specialist", "reply": response.content}


def route_on_intent(state: RoutingState) -> Literal["claims", "policy"]:
    return "claims" if state["intent"] == "claims" else "policy"


graph_builder = StateGraph(RoutingState)
graph_builder.add_node("classify", classify_intent_node)
graph_builder.add_node("claims", claims_specialist_node)
graph_builder.add_node("policy", policy_specialist_node)

graph_builder.set_entry_point("classify")
graph_builder.add_conditional_edges("classify", route_on_intent, {
    "claims": "claims",
    "policy": "policy",
})
graph_builder.add_edge("claims", END)
graph_builder.add_edge("policy", END)

graph = graph_builder.compile()


def route_and_respond(message: str):
    result = graph.invoke({"message": message})
    return result["specialist"], result["reply"]


if __name__ == "__main__":
    test_messages = [
        "What's the status of my auto claim, CLM-3391?",
        "Does my auto policy cover a tow if my car breaks down?",
        "My basement flooded from a burst pipe, am I covered?",
    ]
    for m in test_messages:
        specialist, reply = route_and_respond(m)
        print(f"\nCUSTOMER: {m}")
        print(f"[routed to: {specialist}]")
        print(f"AGENT: {reply}")

# Expected: identical routing/citations to solution.py.
# Compare graph_builder's shape here to route_and_respond()'s if/else in
# solution.py — same decision, but now it's a graph you can visualize,
# extend with more specialist nodes, or checkpoint mid-conversation.
