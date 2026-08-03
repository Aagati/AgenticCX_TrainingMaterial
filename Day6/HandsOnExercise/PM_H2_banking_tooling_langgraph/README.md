# PM · H2 — Banking: Tooling & Actions via LangGraph

**Track:** Banking | **Time box:** ~50 min | **Pattern practiced:** one LangGraph StateGraph, instantiated with two different model providers AND two cost tiers, hardened with safe tool execution — vendor-swap and cost-control as code-level facts, not slides

## What this lab is about
Single-vendor function calling (one model, one interface) is easy to
build and easy to get locked into. This lab builds a "model decides to
call a tool" shape as a LangGraph node — then proves the point of a
modular stack two ways: running the IDENTICAL graph with a Claude node
and a Gemini node (`build_action_graph()`, same graph, `llm_with_tools`
swapped), and running a COST-TIERED variant where a cheap model decides
and a capable model only gets paid for on the path that actually touches
an irreversible action (`build_tiered_graph()`). Tool execution itself is
hardened — an unknown tool or a raised exception degrades to a safe
reply instead of crashing the graph, and `freeze_card` is idempotent.

## Scenario
A banking customer asks about their balance (safe, read-only — just
answer) and then reports a lost card (irreversible — freeze it only after
they confirm).

## Your task
1. `make_agent_node(llm_with_tools)` — decide whether a tool is needed, and
   gate `freeze_card` behind confirmation.
2. `make_execute_node(llm_with_tools)` — actually run the tool (via the
   given `_run_tool_call()` helper, which already handles unknown tools
   and exceptions) and get the natural-language follow-up.
3. `route_after_agent(state)` — the conditional edge: execute, or stop and
   wait for confirmation.
4. `build_action_graph(llm_with_tools)` — wire the two nodes together.
5. `make_tiered_execute_node(cheap_llm_with_tools, capable_llm_with_tools)`
   — same shape as `make_execute_node`, but the follow-up model is chosen
   per tool: cheap for `get_account_info`, capable for `freeze_card`.
6. `build_tiered_graph(cheap_llm_with_tools, capable_llm_with_tools)` —
   same wiring as `build_action_graph`, but the agent node decides using
   the cheap model and the execute node is the tiered one from #5.

## Why this matters
This is the "Gemini vs. the modular stack" trade-off made concrete: one
hop, one vendor, one unified capability set — versus a mix-and-match
stack where the MODEL is just one swappable node behind a common
interface (LangChain's `.bind_tools()` / `.invoke()` contract). The
confirm-gate, the tool execution, the graph shape — none of it cares
which vendor answers. That's not available to you inside a single
native-audio Live session, where the model IS the session. Whether that
trade-off matters depends entirely on whether "swap the model without
touching anything else" is a requirement you actually have.

The cost-tiering piece is the other half of a production argument: not
every node in a graph needs the same model. `_needs_native()`-style
routing decisions (seen in PM_H1) route WHOLE TURNS to cheap vs. expensive
infrastructure; this lab routes WITHIN a single turn — the cheap model
decides and reads, the capable model only gets invoked on the path that
can actually hurt someone if it's wrong. Same underlying idea (don't pay
for capability you don't need), one level more granular.

## Files
- `account_ledger.json` — mock account fixture (balance, deposit, card status).
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install langgraph langchain-anthropic langchain-google-genai python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```
Runs fine with just the above (Claude node real, Gemini node simulated,
tiered graph real — both tiers are Claude, just two model sizes on the
same key). To exercise a real Gemini node:
```bash
export GEMINI_API_KEY=...   # ai.google.dev
```

## Stretch goals
- Replace the two-invoke confirm-gate with LangGraph's real `interrupt()`
  primitive — pause mid-graph at the freeze_card decision and resume with
  a `Command(resume=...)` instead of a second top-level `.invoke()`. Needs
  a checkpointer (`MemorySaver` is enough for this lab) and a thread id.
  This is the idiomatic version of the hack `route_after_agent` currently
  implements — build it once you understand why the hack works.
- Add a retry/fallback edge: make `get_account_info` raise on its first
  call (simulate a transient failure), have the execute node retry once
  before falling back to an apologetic reply — a graph shape for graceful
  degradation instead of a bare try/except.
- Print `graph.get_graph().draw_mermaid()` for `claude_graph` and
  `tiered_graph` side by side — same shape, different node count on the
  execute side (one model vs. a per-call choice) — to see the difference
  is in the closures, not the graph topology.

## Discussion (bring back to the group)
- The confirm-gate here is a two-invoke protocol (ask, then re-invoke with
  `confirmed=True`) rather than an in-graph pause. LangGraph has a real
  `interrupt()` primitive for pausing mid-graph and resuming later — what
  would you need (a checkpointer, at minimum) to use that instead, and
  when would the extra complexity actually be worth it over this simpler
  two-call version?
- `build_tiered_graph()` always uses the CHEAP model to decide which tool
  to call, even when the request might be about `freeze_card`. If the
  cheap model misclassifies — routes a freeze request through as a
  balance lookup, or vice versa — is that a bigger risk than the cost
  savings are worth? Where would you draw the line between "cheap enough
  to trust with routing" and "too risky to let decide anything"?
