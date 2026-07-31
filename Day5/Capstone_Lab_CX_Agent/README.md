# Capstone Lab — Building a Governed, Evaluated CX Agent

This folder holds the 2-hour synthesis capstone (`lab30/`) that closes out
the Agentic AI for CX program: candidates build **ClaimsBot**, a single
insurance claims-support agent that pulls together grounding (Day 1),
governed actions + guardrails (Day 1, Day 4), and trajectory evaluation
(Day 5) into one coherent scenario instead of four separate exercises.

This is the **build** counterpart to
`Day5/HandsOnExercise/06_Postlunch_H3_Team_Capstone_Brief` — that lab
scopes a *new* CX problem on paper; this lab implements a *given* one in
code, end to end, and evaluates it.

## Where to go
See [`lab30/README.md`](lab30/README.md) for the full brief: scenario,
4-part breakdown (Grounded Answers → Governed Actions → Guardrails →
Trajectory Eval), setup, definition of done per part, and stretch goals.

## Layout
```
lab30/
  README.md                    <- full lab brief, start here
  starter/
    lab_capstone.py            <- candidates edit this (look for # TODO)
    knowledge_base.py          <- provided data
    sample_transcripts.py      <- provided data
    requirements.txt
  solution/
    lab_capstone_solution.py   <- facilitator reference, complete
    knowledge_base.py
    sample_transcripts.py
    requirements.txt
```

## Running it
```bash
cd lab30/starter    # or lab30/solution
pip install -r requirements.txt
python lab_capstone.py           # or lab_capstone_solution.py
```
Uses this repo's root `.env` via `load_dotenv()` for `ANTHROPIC_API_KEY` —
no separate key needed if it's already set there. Only Part 1's
`ask_grounded()` calls the model; Parts 2–4 are plain Python and need no
API key.

Every governed action and the Part 4 eval report are also traced to
Langfuse (given scaffolding, not a TODO) — same `LANGFUSE_PUBLIC_KEY` /
`LANGFUSE_SECRET_KEY` from the root `.env`, optional: missing keys degrade
to a no-op, they never block the lab. See `lab30/README.md`'s
Observability section for what gets traced.
