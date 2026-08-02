# Agentic CX Hands-On Exercises — Training Notes

Index into the per-day breakdowns. Each day file covers, per lab: code
structure walkthrough, an expected input → output test matrix, and edge
cases worth exercising when running the lab live or grading a participant's
build.

| File | Scope |
|---|---|
| [Day1_Notes.md](Day1_Notes.md) | Foundations — single-turn → confirm-gated tool → multi-tool escalation loop |
| [Day2_Notes.md](Day2_Notes.md) | Conversation design, multi-agent routing, memory, channel adapters |
| [Day3_Notes.md](Day3_Notes.md) | Voice pipeline — latency, turn-taking, telephony state, reliability, compliance |
| [Day4_Notes.md](Day4_Notes.md) | Enterprise integration, guardrails-as-code, permissions, idempotency, audit |
| [Day5_Notes.md](Day5_Notes.md) | Evaluation, online QA, ROI modeling, eval-gated rollout, governance |

## Setup (applies to all 5 days)

One shared venv + `.env` at repo root — see conversation history / `.gitignore`
for what's tracked. To run any lab:

```bash
.venv/Scripts/python.exe Day<N>_Labs/<lab_folder>/solution.py
```

Day 5's Python labs are the exception — they read data files relative to
their OWN folder, so `cd` into the lab folder first:

```bash
cd Day5_Training_Exercises/Day5_Training_Exercises/01_Prelunch_H1_Insurance_Eval_Suite
../../../.venv/Scripts/python.exe eval_suite_solution.py
```

`requirements.txt` at root is a frozen pin of the venv (`anthropic`,
`python-dotenv`, `openpyxl` + transitive deps) — reinstall with
`.venv/Scripts/python.exe -m pip install -r requirements.txt` if the venv
ever needs rebuilding.

## The week's arc

1. **Day 1** — tool-use ramp: no tools → confirm-before-irreversible-action →
   bounded multi-tool loop with escalation as a legitimate terminal state.
2. **Day 2** — same ramp composed into bigger shapes: multi-agent supervisor
   routing, tiered (semantic/episodic) memory, channel-agnostic cores.
3. **Day 3** — the SAME primitives applied to voice specifically: a latency
   budget, an endpointing/turn-taking heuristic, a telephony state machine,
   then fused together and hardened with STT failover + compliance gates.
4. **Day 4** — every guardrail that was prompt-text through Day 1-3 gets
   rebuilt as a deterministic code-level gate: typed schemas, permission
   lookups, idempotency keys, layered input/output filters, full audit trails.
5. **Day 5** — none of the above gets trusted on vibes: trajectory + resolution
   scoring, lexicon-based online QA, an ROI model tying it to a business case,
   and an eval gate that BLOCKS a rollout on regression or any safety
   violation, no override.
6. **Capstone (Problem Statement 2)** — `Capstone_Telecom_Omnichannel_Agent/`
   fuses Days 1-5 into one graded build: multi-agent handoff (Day 2) over
   MCP tools with idempotency (Day 4), guarded by permissions + layered
   injection defense (Day 4), priced and traced through Langfuse (Day 5).
   Siblings: `Day4/HandsOnExercise/Capstone_Banking_MCP_Agent` (Days 1+4)
   and `Day5/Capstone_Lab_CX_Agent/lab30` (Days 1+4+5) — neither of those
   combines multi-agent teams with the MCP/permissions/injection stack
   under Langfuse observability the way this one does.

## Known pre-existing issues (flagged, not fixed unless asked)

- `Day1_Labs/H1_insurance_chat_agent/solution.py` hardcodes the knowledge-base
  path as `H1_insurance_chat_agent\\knowledge_base.json` — only works if run
  from `Day1_Labs/` as the working directory, unlike its own `starter.py`
  (which uses the correct lab-relative path). Breaks if you `cd` into the H1
  folder and run `solution.py` there.
