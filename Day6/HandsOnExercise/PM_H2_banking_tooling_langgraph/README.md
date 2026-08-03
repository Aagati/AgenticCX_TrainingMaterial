# PM · H2 — Banking: Tooling & Actions via LangGraph

**Track:** Banking | **Time box:** ~40 min | **Pattern practiced:** one LangGraph StateGraph, instantiated with two different model providers, to make "Gemini vs. the modular stack" a code-level fact instead of a slide

## How this compounds on this morning
AM_H3 built real function calling directly against the `google-genai` SDK
(one vendor, one interface). This lab takes the same "model decides to call
a tool" shape and rebuilds it as a LangGraph node — then proves the point
of the modular stack by running the IDENTICAL graph with a Claude node and
a Gemini node. `build_action_graph()` is called twice with two different
`llm_with_tools` arguments; nothing else changes.

## Scenario
A banking customer asks about their balance (safe, read-only — just
answer) and then reports a lost card (irreversible — freeze it only after
they confirm), same tool pair Day 3's AM_H1 used.

## Your task
1. `make_agent_node(llm_with_tools)` — decide whether a tool is needed, and
   gate `freeze_card` behind confirmation.
2. `make_execute_node(llm_with_tools)` — actually run the tool and get the
   natural-language follow-up.
3. `route_after_agent(state)` — the conditional edge: execute, or stop and
   wait for confirmation.
4. `build_action_graph(llm_with_tools)` — wire the two nodes together.

## Why this matters
This morning's Topic 06 (Gemini vs. the modular stack) asked you to weigh
one hop against three (AM_H1) and a unified capability set against a
mix-and-match one. Here's the other side of that trade, concretely: in the
modular stack, the MODEL is just one swappable node behind a common
interface (LangChain's `.bind_tools()` / `.invoke()` contract) — the
confirm-gate, the tool execution, the graph shape, none of it cares which
vendor answers. That's not available to you inside a single native-audio
Live session (AM_H1), where the model IS the session. Whether that
trade-off matters depends entirely on whether "swap the model without
touching anything else" is a requirement you actually have.

## Files
- `account_ledger.json` — mock account fixture (same shape as Day 3's).
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install langgraph langchain-anthropic langchain-google-genai python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```
Runs fine with just the above (Claude node real, Gemini node simulated).
To exercise a real Gemini node:
```bash
export GEMINI_API_KEY=...   # ai.google.dev
```

## Stretch goals
- Add a THIRD `build_action_graph()` instantiation using a cheaper/smaller
  model for the balance-lookup path only, and route between "cheap model
  for read-only, capable model for anything touching freeze_card" — a
  realistic cost-control move that the graph-based structure makes easy to
  bolt on.
- Print `graph.get_graph().draw_mermaid()` for both graphs (they're
  identical) to literally see "same graph, different node" instead of
  reading it in this README.

## Discussion (bring back to the group)
- The confirm-gate here is a two-invoke protocol (ask, then re-invoke with
  `confirmed=True`) rather than an in-graph pause. LangGraph has a real
  `interrupt()` primitive for pausing mid-graph and resuming later — what
  would you need (a checkpointer, at minimum) to use that instead, and
  when would the extra complexity actually be worth it over this simpler
  two-call version?
