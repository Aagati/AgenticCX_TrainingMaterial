# Capstone Lab: Building a Governed, Evaluated CX Agent

**Time:** 2 hours · **Level:** Medium · **Audience:** Engineering graduates who have completed Days 1–5 of Agentic AI for CX

## Scenario

You're building **ClaimsBot**, a claims-support agent for a general-insurance
company. Across four parts, you'll implement the same core patterns this
whole program has been teaching — grounded knowledge, governed actions,
guardrails, and evaluation — applied to one coherent scenario instead of
four disconnected exercises.

This lab is intentionally a *synthesis* exercise: each part pulls together
concepts from more than one training day, the same way a real production
agent has to.

## What each part draws on

| Part | Time | Concepts | Day(s) |
|---|---|---|---|
| 1 — Grounded Answers | 25 min | Retrieval, citations, hallucinated-citation checking | Day 1 |
| 2 — Governed Actions | 35 min | Typed tools, dual-gate authorization, idempotency, confirmation gates | Day 1, Day 4 |
| 3 — Guardrails & Escalation | 30 min | Indirect prompt injection, output guardrails, validated handoff payloads | Day 1, Day 4 |
| 4 — Trajectory Eval | 20 min | Four-dimension rubric, pass/fail + failure-mode reporting | Day 5 |
| Wrap-up | 10 min | Definition of done, reflection | All |

Every governed action, the grounded model call, and the Part 4 eval report
are also traced to **Langfuse** (given, not a TODO — see [Observability](#observability-given-not-a-todo)
below) — the same tracing/scoring pattern the Day 5 morning eval suite lab
uses, applied here to a full agent's actions instead of a standalone
scorer.

## Setup (do this before the clock starts)

```bash
cd starter
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # only needed for Part 1's live model call
```
`load_dotenv()` also picks up `ANTHROPIC_API_KEY` from the `.env` file at
the repo root, so no `export` is needed if it's already set there. The same
file's `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`
are picked up too, for the tracing described below.

You do **not** need a working API key to complete Parts 2, 3, or 4 — every
check in those parts is plain Python logic you can test directly. Only
`ask_grounded()` in Part 1 calls the model. Langfuse tracing is optional on
top of that: no Langfuse keys set means the run just prints a one-line
notice instead of a dashboard link — nothing blocks or errors.

Files you'll edit: **`starter/lab_capstone.py`** only. Everything else
(`knowledge_base.py`, `sample_transcripts.py`) is provided data — read it,
don't edit it.

---

## Part 1 — Grounded Answers With Citations (25 min)

Implement:
- `retrieve(query, kb, top_k=2)` — simple keyword-overlap retrieval over
  `POLICY_CLAUSES` (six insurance policy clauses, provided in
  `knowledge_base.py`).
- `ask_grounded(question)` — calls the model with only the retrieved
  clauses, parses its JSON reply into a `GroundedAnswer`, and **validates
  that every cited `doc_id` was actually retrieved** — a schema check alone
  can't catch a hallucinated citation; you have to check it against what
  was actually given to the model.

**Test it:**
```bash
python lab_capstone.py
```
Ask yourself: if you retrieved `POL-103` and `POL-106`, and the model cites
`POL-101`, what should happen? (That's the exact case your validation step
needs to catch.)

**Definition of done:** `ask_grounded()` returns a real answer with correct
citations for at least two different questions, and raises/flags on a
manufactured case where the model is told to cite something outside the
retrieved set.

---

## Part 2 — Typed Action + Dual-Gate Authorization + Idempotency (35 min)

Implement:
- `check_authorization(user_id, policy_id, claim_amount)` — **Gate 1
  (Ownership):** does this policy belong to this user? **Gate 2
  (Capability):** is the policy active, is the amount within the Sum
  Insured, has the claims-per-period limit not been hit? Both gates must
  pass — checking ownership alone is the "Ownership Only" fallacy from
  Day 4.
- `file_claim(...)` — validates typed input, blocks if not `confirmed`,
  returns the *stored* result on a repeated `idempotency_key` instead of
  re-filing, then runs the dual-gate check before actually filing.

**Test it:** the `__main__` block already exercises three authorization
cases (allowed, wrong owner, claims-limit hit) and an idempotent retry —
run the file and check the output matches what you'd expect from each
case.

**Definition of done:** a claim from the true owner, within limits, with
`confirmed=True` succeeds; the same call repeated with the same
`idempotency_key` returns the identical result without incrementing the
claim counter; an unconfirmed call is blocked before authorization is even
checked; a non-owner or over-limit call is denied with a clear reason.

---

## Part 3 — Guardrails Against Injection + Escalation (30 min)

`knowledge_base.py` includes a `POISONED_DOC` — a support note with a
hidden instruction trying to get the agent to leak *other* customers'
policy numbers. This is **indirect** injection (Day 4): it arrives via a
retrieved document, not the customer's typed message, so an input filter
that only scans what the customer typed would never see it.

The walkthrough (`__main__`) prints the exact instruction hidden inside
`POISONED_DOC` and then tests `output_guardrail()` against a reply that
simulates what a model would say if it complied — no live model call
needed to see the guardrail work. If you want to see whether a *real*
model falls for the injection, try feeding `POISONED_DOC` into
`ask_grounded`'s retrieved-clauses block yourself as a stretch exercise.

Implement:
- `output_guardrail(reply_text, allowed_policy_id)` — scans the model's
  *reply* for any `PA-####`-shaped policy id other than the one the
  customer is actually asking about, and blocks the reply if it finds one.
- `EscalationPayload.not_placeholder` — a Pydantic field validator that
  rejects empty strings and placeholder values (`"TBD"`, `"N/A"`,
  `"UNKNOWN"`), mirroring Day 1's escalation-payload validation.
- `escalate_to_human(...)` — validates and files an escalation ticket.

**Test it:** the `__main__` block includes a "safe" reply and a "leaky"
reply that mentions a second policy id — confirm your guardrail passes one
and blocks the other.

**Definition of done:** the guardrail blocks the leaky reply and allows the
safe one; `escalate_to_human` raises on a placeholder field and succeeds on
a real one.

---

## Part 4 — Mini Trajectory Eval (20 min)

`sample_transcripts.py` has six pre-written conversations. Implement
`evaluate_transcript(transcript)`, scoring the same four dimensions Day 5
taught:

- **task_completion** — does it end with a real reply, not a dead end?
- **policy_adherence** — was every informational claim cited, and was
  every `file_claim` call preceded by an actual confirm exchange?
- **tool_call_correctness** — was the *right* tool used (a claim over the
  escalation limit should escalate, not auto-file), and is any
  `escalate_to_human` payload actually valid?
- **step_efficiency** — did the agent avoid asking for the same
  information twice?

Run `run_eval_report()` (already wired into `__main__`) once you're done.

**Notice something on purpose:** all six transcripts pass `task_completion`
— including the buggy ones. That's the whole point of Day 5's lesson:
"the customer got an answer" never tells you whether the *path* to that
answer was sound. Only the other three dimensions catch the five bugs
planted in this set.

**Definition of done:** your report shows **exactly 2 of 6** transcripts
(`T1_clean` and `T5_correct_escalation`) passing all four dimensions, and
each of the other four failures names the specific problem in `notes`
(missing confirmation, missing citation, wrong tool for a high-value
claim, or a redundant re-ask).

---

## Observability (given, not a TODO)

`file_claim`, `escalate_to_human`, `ask_grounded`, and the Part 4 eval loop
are all decorated with `@traced(...)` (a thin wrapper around Langfuse's
`@observe` — see the top of `lab_capstone.py`). You don't implement or
edit any of this; it wraps around whatever you write for the TODOs above.

- **`file_claim` / `escalate_to_human` / `ask_grounded`** — traced as-is;
  Langfuse auto-captures each call's arguments as `input` and its return
  value as `output`, so every filed claim, denial, idempotent replay,
  escalation, and grounded answer becomes an inspectable trace.
- **Part 4's eval loop** — each transcript gets its own trace with all
  four dimension scores (`task_completion`, `policy_adherence`,
  `tool_call_correctness`, `step_efficiency`) plus `passed` logged as
  NUMERIC scores via `score_current_trace()` — the exact same pattern the
  Day 5 morning eval suite lab uses for its LLM-judge scores, so you can
  filter/sort the six transcripts in the Langfuse UI instead of only
  reading the printed report.
- **Optional by design** — if `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
  aren't set, `traced()` degrades to a no-op decorator and the run just
  prints a one-line notice instead of a dashboard link. This keeps Parts
  2-4's "zero API key needed" promise intact — Langfuse is additive
  observability, never a requirement to finish the lab.

Run the full walkthrough (`python lab_capstone.py` or
`lab_capstone_solution.py`) with the Langfuse keys set and open the
printed URL afterward — you should see one trace per `file_claim` /
`escalate_to_human` call from Parts 2-3, one generation trace for
`ask_grounded` from Part 1, and six scored traces (`eval_T1_clean` …
`eval_T6_inefficient_repeat_ask`) from Part 4.

---

## Wrap-Up (10 min) — Reflection

Discuss with your table, or answer for yourself:

1. Which part took longest, and was that the part you expected?
2. In Part 4, two different transcripts (T2 and T3) both failed
   `policy_adherence` for two *completely different* reasons. Why does it
   make sense for one dimension to catch more than one kind of bug, rather
   than giving every distinct rule its own dimension?
3. If you had a 7th transcript to design, what bug would you plant that
   none of the current four dimensions would catch? (Hint: think about
   what Day 5's real rubric checks that this simplified version doesn't.)
4. Every check you wrote today runs as plain Python — none of it depends
   on the model "deciding" to be safe. Why does that matter more for
   `check_authorization` and `output_guardrail` than it does for the
   wording of a system prompt?

## Stretch Goals (if you finish early)

These aren't required, but each one pulls in a concept from a day this
core lab didn't have time for:

- **Day 2 (Memory):** add a `CUSTOMER_MEMORY` dict that remembers a
  customer's preferred contact method across two separate calls to
  `ask_grounded`, and inject it into the system prompt.
- **Day 2 (Multi-agent):** split `ask_grounded` into a router that sends
  coverage questions to one persona and claim-status questions to another,
  each with its own system prompt.
- **Day 3 (Latency):** wrap `ask_grounded` with `time.perf_counter()` calls
  and report time-to-first-token vs. total latency, the same distinction
  Part 1's timing bug in Day 3's lab was built to catch.
- **Day 4 (MCP-style tools):** rewrite `file_claim` and
  `escalate_to_human`'s signatures as JSON Schema tool definitions and wire
  them into a real `client.messages.create(..., tools=[...])` loop so the
  model chooses which to call, instead of you calling them directly.

## File Reference

```
starter/
  lab_capstone.py        <- you edit this (look for `# TODO`)
  knowledge_base.py      <- provided data, do not edit
  sample_transcripts.py  <- provided data, do not edit
  requirements.txt
solution/
  lab_capstone_solution.py   <- complete reference implementation
  knowledge_base.py
  sample_transcripts.py
  requirements.txt
```
