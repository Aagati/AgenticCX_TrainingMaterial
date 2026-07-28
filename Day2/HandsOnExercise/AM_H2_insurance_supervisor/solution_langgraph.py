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
import os
import sys
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

load_dotenv()  # ChatAnthropic reads ANTHROPIC_API_KEY from the environment

# Windows consoles default to cp1252 and will crash on the model's em-dashes
# and curly quotes. Force UTF-8 so the lab doesn't die on a print().
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "claude-sonnet-5"
llm = ChatAnthropic(model=MODEL, max_tokens=300)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DATA_DIR, "mock_data.json")) as f:
    DATA = json.load(f)


class RoutingState(TypedDict):
    """The state every node reads from and writes to.

    This is the core difference from solution.py. There, state lived in local
    variables inside route_and_respond(). Here it's a declared, typed object
    that flows through the graph — which is what makes the graph inspectable,
    checkpointable (pause mid-conversation, resume later), and safe to extend
    with ten more nodes without threading arguments through everything.
    """
    message: str
    intent: str
    specialist: str
    reply: str


# Nodes are plain functions: state in, PARTIAL state out. Returning
# {"intent": ...} merges that key into the state — you never mutate or
# rebuild the whole object.

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
    """The edge function. This is solution.py's if/else, pulled out into a
    named function so the graph — not the calling code — owns the decision.
    It returns a LABEL, not a node; the mapping from label to node is declared
    below, so you can rewire the graph without touching this logic."""
    return "claims" if state["intent"] == "claims" else "policy"


# ---------- Wiring the graph ----------
#
# Everything above is just functions. This block is where the control flow
# lives, declared once and in one place. In solution.py that control flow is
# scattered across route_and_respond()'s body; here you can print it, draw it,
# or hand it to someone non-technical.

graph_builder = StateGraph(RoutingState)
graph_builder.add_node("classify", classify_intent_node)
graph_builder.add_node("claims", claims_specialist_node)
graph_builder.add_node("policy", policy_specialist_node)

graph_builder.set_entry_point("classify")
# Conditional edge: run route_on_intent, then jump to the node its returned
# label maps to. The dict is the label->node mapping.
graph_builder.add_conditional_edges("classify", route_on_intent, {
    "claims": "claims",
    "policy": "policy",
})
# Both specialists terminate. Point them at a "summarize" node instead and
# you'd have the full supervisor pattern — that's the extension PM_H1 builds.
graph_builder.add_edge("claims", END)
graph_builder.add_edge("policy", END)

# compile() validates the graph (unreachable nodes, missing edges) once at
# import time rather than failing on some unlucky message in production.
graph = graph_builder.compile()


def route_and_respond(message: str):
    # Same signature as solution.py's route_and_respond — the swap from
    # if/else to graph is invisible to callers. Only "message" is supplied;
    # the other RoutingState keys get filled in by nodes as the graph runs.
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
