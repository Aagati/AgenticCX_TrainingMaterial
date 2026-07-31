# Pre-Lunch · H1 — Insurance: Resolution + Trajectory Eval Suite

**Track:** Insurance | **Time box:** 25–35 min | **Ships:** a working eval suite with Langfuse-traced, LLM-judged results
**Pattern practiced:** two independent eval lenses (outcome vs. process), combined into one triage score

## Objective
Score each of the 10 golden insurance-support conversations in `goldens.json` on two independent lenses — did it **RESOLVE** the customer's problem (outcome), and did the agent follow the correct **TRAJECTORY** of tool calls (process)? Combine both into a single triage score and flag the conversations that need human review.

Every golden is also traced through Langfuse with a real LLM-as-judge pass over the agent's final reply, so a facilitator can open the Langfuse UI afterward and see per-conversation traces with all four scores attached — not just a terminal table.

## Steps
1. Open `goldens.json` and read through all 10 conversations. Note which ones look suspicious to you before you write any code — this is your intuition check.
2. Open `eval_suite_starter.py`. Implement `resolution_score()` using the `expected_resolution` field.
3. Implement `trajectory_score()` by comparing `agent_actions` to `expected_actions`. Decide your own rule for partial credit on redundant-but-harmless extra calls versus missing or out-of-order required calls.
4. Implement `combined_score()` — choose and justify a weighting between resolution and trajectory.
5. Run `python eval_suite_starter.py` and review the printed report, plus the traces it produces in Langfuse. Do the flagged conversations match your intuition from Step 1?
6. Look closely at **G02** and **G08** in the report: both have real policy violations (identity not verified, coverage not checked) but still resolved the customer's issue. Did your threshold catch them? If not, would you change your weighting or your flag threshold — and what would that trade off?

## Setup
```bash
pip install langfuse anthropic pydantic python-dotenv
```
Set `ANTHROPIC_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` in the `.env` file at the repo root (`cloud.langfuse.com` has a free tier; placeholders should already be there). `load_dotenv()` walks up from the lab folder to find it — no per-lab `.env` needed.

## Run
```bash
cd 01_Prelunch_H1_Insurance_Eval_Suite
python eval_suite_starter.py      # participant version — raises NotImplementedError until the 3 TODOs are filled in
python eval_suite_solution.py     # facilitator reference — runs end-to-end
```

## What "ships" means
A per-conversation report printed to the console — resolution score, trajectory score, combined score, LLM-judge score (1–5), and a review flag for anything below 0.6 combined or ≤2 on the judge — plus one Langfuse trace per golden carrying all four scores. And a one-line verbal answer to the Step 6 question, ready to share with your table.

## Files
- `goldens.json` — 10 golden conversations: each has the agent's actual actions (`agent_actions`), the policy-correct actions (`expected_actions`), a ground-truth resolution flag (`expected_resolution`), and the agent's final reply text.
- `eval_suite_starter.py` — 3 TODOs (`resolution_score`, `trajectory_score`, `combined_score`); the Langfuse tracing and `llm_judge_score()` LLM-as-judge call are given as working scaffolding, wired to call your scorers once they're implemented.
- `eval_suite_solution.py` — facilitator reference with all 3 TODOs filled in, same Langfuse + judge wiring.

## Stretch goal (optional)
Extend `trajectory_score` so a *redundant but harmless* extra tool call (see **G04**) is penalised less than a *missing required* tool call or an *out-of-order* one (see **G02**, **G08**).

## Facilitator tips
- If a pair finishes early, point them at the stretch goal above.
- The facilitator solution is intentionally **not** a single "correct" answer — several reasonable weighting schemes exist. Push participants to defend their choice rather than converge on one number.
- The LLM-judge call and Langfuse wiring are given code, not a TODO — the pedagogical focus stays on the two scoring lenses. Use the judge's `rationale` output during the Step 6 discussion; it usually independently corroborates the G02/G08 policy violations.
