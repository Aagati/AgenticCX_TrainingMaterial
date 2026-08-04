# Day 8 — CX Analytics, Personalisation & Continuous Improvement

Four labs, same shape Day 7 established: **Lab-1 and Lab-2 are the
compounded, facilitator-led labs** (the two richest, densest in new
mechanics), **Lab-3 is self-paced and deliberately lightweight** (safe to
skip entirely — nothing downstream depends on it), and the **Capstone**
fuses everything into one LangGraph, tested by its own built-in
self-check.

Every lab assumes `ANTHROPIC_API_KEY` is configured — Day 8 is Claude-only,
same convention Day 7 held. `Lab2` and the `Capstone` additionally use
`langgraph`/`langgraph`-adjacent patterns; the `Capstone` is the only lab
this day with a real `langgraph` dependency.

Run from repo root: `.venv/Scripts/python.exe Day8/HandsOnExercise/<lab>/solution.py`

---

## Labs

| Folder | Lab | Industry | Facilitator pacing | Topics covered |
|---|---|---|---|---|
| `Lab1_Telecom_Conversation_Analytics` | Nobody Can Tell You Which Conversations Are Failing | Telecom | **Led live** | Conversation analytics & insights, metrics that matter, analytics pipeline, dashboards |
| `Lab2_Banking_Personalisation_QA_Loop` | Ship a Smarter Offer Engine Without Shipping a Bad One | Banking | **Led live** | Continuous QA, QA automation, trace mining → goldens, eval-gated updates, the improvement loop, **personalisation engines, personalisation in the loop** |
| `Lab3_Retail_Knowledge_Management` | Half the Knowledge Base Is Out of Date and Nobody Noticed | Retail | Self-paced, safe to skip | Knowledge management |
| `Capstone_Insurance_Improvement_Loop` | Prove the Loop Works Before a Real Customer Sees It | Insurance | Capstone (combine-all, self-graded) | Every topic above, fused |

## Why personalisation moved into Lab-2

Personalisation doesn't have a natural mechanical home in an analytics
lab (Lab-1) — dashboards and metrics don't need a ranking engine to exist.
It DOES have one in continuous QA: a personalised offer-ranking engine is
exactly the kind of thing that needs mining, goldens, and an eval gate
before a change to it ships. So Lab-2 carries 7 of this day's 12 topics —
personalisation engines and personalisation-in-the-loop are taught as the
THING being continuously QA'd, not as a separate bolted-on lab. This also
protects the topic from Lab-3's self-paced risk: personalisation is fully
covered in a facilitator-led lab regardless of whether Lab-3 ever happens.

## What compounds into what

The Capstone doesn't cross-import Lab1-3's code — it re-implements a thin,
insurance-flavored version of each primitive, the same "compound, don't
cross-import" rule Day 7's capstone followed:

- `KnowledgeBase` — Lab-3's retrieval idea, thinned, shipped as GIVEN code
  (not a TODO) specifically because Lab-3 is the lab most likely to have
  been skipped.
- `AnalyticsEngine` / `Dashboard` — Lab-1's metrics-then-chart pattern,
  re-run over a claims log instead of a conversation log.
- The QA check registry, `QAMiner`, `GoldenBuilder`, the eval gate —
  Lab-2's continuous-QA loop, re-implemented for insurance claim
  responses instead of banking offers, with one deliberate change (mining
  excludes the LLM-judge check, for reproducibility — see the Capstone's
  own README for why).
- A LangGraph `StateGraph` for the one part that's genuinely per-item and
  cyclic — draft, judge, and (if it fails) revise and judge again — wiring
  the response agent and eval gate from Lab-2 into an actual graph edge
  rather than a hand-rolled while-loop.

## New this day: SDK surface and production patterns

| What | Where | Why it's new |
|---|---|---|
| Message **Batches API** | Lab-1 | 24 requests as one job, not a loop of 24 — the correct default for offline/analytics scoring workloads |
| **Prompt caching** (`cache_control`) | Lab-2 | A large, reused-every-call system-prompt block (the offer catalog) is exactly what a cache breakpoint is for |
| **matplotlib dashboards** | Lab-1, Capstone | First use of real chart rendering in this curriculum — see each lab's README for the color/form rules applied |
| **Registry + decorator patterns** | Lab-2, Capstone | `@register_check(...)` (plugin registry) and `@eval_gated(...)` (a decorator that attaches a capability, not just wraps a call) — production shapes for "pluggable checks" and "gate this before it ships" |
| **Weighted scoring, not if/elif** | Lab-2, Lab-3 | Personalisation ranking and KB relevance are both multi-factor formulas over hard-filtered survivors, not a chain of conditionals |

## Persistent memory, every lab

Every lab writes its own history to a dedicated JSON file — never an
in-process dict — so a second run shows a trend, not a snapshot that dies
with the process:

| Lab | File | What it holds |
|---|---|---|
| `Lab1` | `analytics_runs.json` | One record per run: metrics + insight-stats snapshot |
| `Lab2` | `goldens.json` / `eval_runs.json` | Mined failures promoted to durable test cases; every gate verdict |
| `Lab3` | `kb_usage_log.json` | Every query answered, what was cited, any staleness flags |
| `Capstone` | `capstone_goldens.json` / `capstone_eval_runs.json` | Same shape as Lab-2, scoped to its own insurance fixture |

All of these are gitignored and created at runtime — delete any of them to
reset that lab to a cold start.

## Running the labs

Each lab folder has a `starter.py` (TODOs to fill in) and a `solution.py`
(reference, runs end-to-end).

```bash
cd Lab1_Telecom_Conversation_Analytics
python starter.py       # participant version
python solution.py      # reference — runs end-to-end
```

**Setup, all labs:**
```bash
pip install anthropic pydantic python-dotenv matplotlib langgraph
export ANTHROPIC_API_KEY=sk-ant-...
```

## How each lab ties back to the day's topics

- **Lab-1 Telecom** → Conversation analytics & insights, metrics that
  matter, analytics pipeline, dashboards
- **Lab-2 Banking** → Continuous QA, QA automation, trace mining →
  goldens, eval-gated updates, the improvement loop, personalisation
  engines, personalisation in the loop
- **Lab-3 Retail** → Knowledge management
- **Capstone Insurance** → Every topic above, fused into one graph, tested
  by its own self-check

See `Day8_Notes.md` for the full facilitator test-matrix/edge-case
companion, in the same format as `Day7_Notes.md`.
