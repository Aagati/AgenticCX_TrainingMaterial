# PM · H2 — Insurance: Defence-in-Depth Guardrail Stack + Replayable Audit Trail

**Track:** Insurance | **Time box:** ~45 min | **Ships:** an auditable agent
**Pattern practiced:** composing independent guardrail layers into one pipeline, with a complete replayable log of every step

## Scenario
This morning's H2 built two guardrail functions in isolation. This
afternoon you compose them — plus a third layer, tool-scoping — into one
defended pipeline, and instrument EVERY step so a security reviewer could
replay exactly what happened for any conversation, months later, without
guessing.

## Your task
Build `defended_agent_turn(user_message, retrieved_doc)` as a pipeline
with these layers, EACH logged as its own step in `AUDIT_TRAIL`. Structure
the input and output checks as **lists of layers** (`INPUT_LAYERS`,
`OUTPUT_LAYERS` — each a list of `(name, check_fn)` tuples run in order by
a shared `run_layers()` helper) rather than hardcoding each check as its
own `if` statement in the main flow. The point: adding a fifth guardrail
next month should mean appending one tuple to a list, not editing the
control flow of `defended_agent_turn()`.
1. **Input layer(s)** (reuse this morning's `input_guardrail` logic, now
   as a layer function). Log each check and its result.
2. **Scoped system prompt** treating `retrieved_doc` as untrusted (reuse
   this morning's pattern). Log the reasoning-relevant parts: what
   document was provided, what the model was told about it.
3. **Output layer(s)** (reuse this morning's `output_guardrail` logic,
   split into layer functions — e.g. one for leaked-instruction phrases,
   one for persona breaks). Log each check and its result.
4. **Tool-scoping** — even though this agent doesn't need real tools
   today, add a `flag_for_review` tool the model can call instead of
   answering if it's uncertain the input is safe, and log if it's used.

Each layer's log entry should include enough detail that
`replay_audit_trail(AUDIT_TRAIL)` — a function you also write — can print
a clean, chronological, human-readable narrative of the ENTIRE turn:
what came in, which layer (by name) checked it and with what result, what
the model was told, what it produced, what was checked on the way out,
and the final outcome — including exactly which layer blocked it, if any did.

Run it against one clean case and one adversarial case (reuse
`malicious_kb_docs.json` from this morning) and show the two audit trails
side by side.

## What "ships" means
A working `defended_agent_turn` plus a `replay_audit_trail` function that
turns `AUDIT_TRAIL` into a readable step-by-step account — for both a
clean run and a blocked/flagged run.

## Files
- `starter.py` — scaffold with TODOs. Includes copies of this morning's
  `input_guardrail` / `output_guardrail` so this lab is self-contained.
- `malicious_kb_docs.json` — same attack documents as this morning.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Export `AUDIT_TRAIL` to a JSON file per conversation, keyed by a
  conversation id — the shape a real logging/SIEM pipeline would ingest.
- Add a severity field to flagged entries and have `replay_audit_trail`
  highlight high-severity entries differently from routine passes.
- Prove the pipeline is actually extensible: add a THIRD input layer
  (e.g. a length check rejecting messages over 2000 characters) as a
  single new tuple in `INPUT_LAYERS`, with zero changes to
  `defended_agent_turn()`. If you have to touch the control flow to add
  it, the pipeline isn't actually decoupled yet.

## Discussion (bring back to the group)
- If a security incident happened three weeks ago, what does your audit
  trail need to contain for someone to reconstruct — without re-running
  anything — exactly what the agent saw, decided, and said? What's
  missing from today's build?
