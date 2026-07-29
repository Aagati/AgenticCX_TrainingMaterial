# PM · H1 — Insurance: Supervisor + 2 Specialist Agents

**Track:** Insurance | **Time box:** ~75 min | **Ships:** a routed multi-agent CX flow
**Pattern practiced:** supervisor orchestration with real tool-calling handoffs, scoped specialist tools, and an agent-assist mode

## Scenario
This morning (AM · H2) you built a lightweight supervisor that classified
intent and called one of two specialist *functions*. That's the concept.
This afternoon you build the real architecture: a supervisor that hands off
to specialist **sub-agents**, each of which has its **own tools** and runs
its **own reasoning loop** — not just a different system prompt string.

## Part 1 — Autonomous routing (build this first)
Build three agents:

1. **Claims Specialist** — has a tool `get_claim_status(claim_id)`. Given a
   customer message, it should figure out (from the message or by asking)
   which claim, call the tool, and answer using the result.
2. **Policy Specialist** — has a tool `search_policy(query)` that does
   simple keyword retrieval over `policy_clauses.json` and returns matching
   clauses. It must answer only from retrieved clauses and cite ids (same
   grounding discipline as Day 1 and this morning).
3. **Supervisor** — has one tool, `handoff(specialist, task)`, where
   `specialist` is `"claims"` or `"policy"`. When the supervisor calls this
   tool, your code should actually **run** the chosen specialist's full
   agent loop (including its own tool calls) on the customer's message, and
   feed the specialist's final answer back to the supervisor as the tool
   result — the supervisor then relays it to the customer in its own voice.

This is a real two-level agent hierarchy: supervisor → specialist → its own
tool. Build it with the plain `anthropic` SDK tool-use loop (the same
mechanics work if you later port it to LangGraph or the Claude Agent SDK —
today's goal is to understand the mechanics, not memorize a specific
framework's API).

## Part 2 — Agent-assist mode (required — this is today's Topic 03)
This morning's deck named "agent-assist mode" as a pattern: the agent drafts
for a human to review instead of replying to the customer directly. Part 1
never actually builds that — Part 2 does.

Add `run_supervisor_agent_assist(customer_message)`, which runs the SAME
routing and specialist research as Part 1, but instead of returning the
reply text directly, returns an `AgentAssistPayload`:
- `recommended_response: str` — the draft a human agent could send as-is or edit.
- `proposed_specialist: Optional[str]` — which specialist was consulted, if any.
- `proposed_task: Optional[str]` — the task that was passed to that specialist.
- `requires_human_approval: bool` — always `True` here; nothing reaches the
  customer without a human sending it.

The specialist research (tool calls, grounding) still happens automatically
— agent-assist mode changes the trust boundary at the LAST step only (who
sends the message), not whether the agent is allowed to look things up.

## What "ships" means
By the end of this lab you should be able to run `python solution.py` (or
your own `starter.py`) and see, end to end: Part 1's autonomous flow for at
least one claims and one policy question, AND Part 2's
`run_supervisor_agent_assist` producing a structured, human-reviewable
payload for the same kind of question.

## Files
- `claims_data.json`, `policy_clauses.json` — mock data for each specialist.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic pydantic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a third specialist (e.g. Billing) and have the supervisor's tool
  schema support it without changing the handoff execution logic.
- Have the supervisor pass along conversation history so a specialist can
  ask a clarifying follow-up and get the customer's next message routed
  back to the *same* specialist instead of re-classifying from scratch.

## Discussion (bring back to the group)
- What did the supervisor's system prompt need to say about *when not* to
  hand off — i.e., handle something itself (like "hello" or "thank you")?
  Multi-agent systems still need a "no handoff needed" path.
- Part 2 only changes the LAST step of the loop. What's the argument for
  putting the human-approval gate there specifically, rather than after
  every internal tool call the specialist makes?
