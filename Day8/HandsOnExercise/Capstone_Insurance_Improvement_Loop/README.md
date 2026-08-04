# Capstone: Insurance - Prove the Loop Works Before a Real Customer Sees It

**Track:** Insurance | **This is the fusion lab** — every mechanic from
Lab-1/Lab-2/Lab-3, fused into one cycle that mines its own mistakes, fixes
them, and proves the fix before shipping it

## Read this first if you never got to Lab-3

Lab-3 was this day's self-paced lab. There's a real chance you're reading
this having never opened it. That's fine by design — `KnowledgeBase` below
ships complete and explained; you don't need to have built one yourself to
understand what it's doing or to use it correctly. What this capstone
actually TESTS is Lab-1 (analytics) and Lab-2 (QA/mining/personalisation/
eval-gating) — the two facilitator-led labs — because those are the ones
you can reasonably be expected to have seen explained live.

## Mental model: a graph, but only where it earns it

```
claim_traces.json (10 historical claim-support sends)
        │
        ▼
AnalyticsEngine.compute()  ──►  Dashboard.build()          <- Lab-1, plain batch Python
        │                                                     (no branching, no graph needed)
        ▼
QAMiner.mine()  ──uses──►  QA registry, deterministic-only  <- Lab-2, same reasoning
        │                    (mining judges FACTS, not opinions)
        ▼
GoldenBuilder.promote()  ──►  capstone_goldens.json
        │
        ▼
for each NEW golden customer:            <- HERE is where a graph earns its keep —
   ┌─────────────────────────┐              everything above is straight-line batch
   │  response_agent          │             work; this part branches AND cycles.
   │  (KnowledgeBase[given]    │
   │   + personalisation +     │
   │   drafting)                │
   │         │                  │
   │         ▼                  │
   │  eval_gate                 │
   │  (FULL registry,           │
   │   judge included)          │
   │    │pass        │fail      │
   │    ▼             ▼         │
   │  promote     repair_attempted?
   │              │no        │yes
   │              ▼          ▼
   │           revise     reject
   │              │
   │              └──loops back to── eval_gate
   └─────────────────────────┘
```

Analytics and mining are BATCH operations — they run once, over everything,
with no per-item decision to make. LangGraph buys nothing there. The
per-golden cycle is different: draft, judge, and — if it fails — revise and
judge AGAIN, capped at one retry. That's an actual cycle in the execution
graph, the one thing a flat function chain can't express as cleanly as a
real edge back to the judging node.

## Given vs. build, and why the split is where it is

| Given | Build | Why |
|---|---|---|
| `KnowledgeBase` | — | Lab-3's idea — the lab most likely to have been skipped |
| `GoldenBuilder`, registry infra | 3 deterministic checks + judge check | The MECHANISM (Lab-2) is given; what gets registered is yours |
| `Dashboard.build` | `AnalyticsEngine.compute` | Chart-drawing is repeated boilerplate; the metrics ARE Lab-1 |
| `revise_node`, `promote_node`, `reject_node` | `response_agent_node`, `eval_gate_node` | The repair loop's MECHANICS aren't new this day; drafting + gating are exactly Lab-2 |
| `capstone_selfcheck`, `demo_repair_loop` | `ImprovementCommandCenter._build_graph` | Grading harness isn't yours to edit; graph wiring is real LangGraph practice |

If a piece tests something Lab-1 or Lab-2 actually walked you through live,
it's a TODO. If it's Lab-3's territory, or infrastructure that was never
this day's teaching point, it's given.

## The self-check is the day's own lesson, pointed at you

`capstone_selfcheck()` re-derives everything from `claim_traces.json`
directly — it doesn't trust `capstone_goldens.json`'s accumulated state, so
it gives the same verdict on your first run or your fiftieth. It hard-
asserts only what's DETERMINISTIC (mining finds exactly 4 customers;
your fresh responses clear policy-type/banned-phrase/disclosure checks). It
reports `relevance_judge`'s opinion on each response without grading it —
a live model's judgment isn't a fact about whether your code is correct.
That split (grade the deterministic facts, report the opinion) is the exact
lesson Lab-2's `eval_gated` was built around — this capstone just runs it
against your submission instead of a personalisation engine.

## Why mining excludes the judge (a deliberate change from Lab-2)

Lab-2 let `relevance_judge` run during mining too, and real testing there
showed it adding EXTRA failures beyond the deterministic ones — authentic
behavior, but it means Lab-2's mining step isn't fully reproducible run to
run. That's fine for a discussion-driven lab; it's a bad property for a
step this capstone's own grading depends on. `QAMiner.mine` here calls
`run_checks(..., deterministic_only=True)` — mining judges what already
happened, and that should be a fact, not a rotating opinion.

## Files
- `insurance_kb_articles.json` — 10 policy articles (auto/home/health +
  general), the required disclosure, banned phrases.
- `insurance_customers.json` — 8 customers, each with a pending question.
- `claim_traces.json` — 10 historical claim-support sends (5 clean, 5
  deterministically bad — 2 wrong policy-type, 2 banned phrase, 1 missing
  disclosure).
- `capstone_goldens.json` / `capstone_eval_runs.json` / `capstone_dashboard.png`
  — created at runtime; gitignored. Delete any of them to reset.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv matplotlib langgraph
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## What you'll build (starter.py)
1. Three deterministic QA checks + the LLM-judge check — the registry
   itself (with its deterministic/non-deterministic split) is given.
2. `AnalyticsEngine.compute` — the batch metrics feeding the dashboard.
3. `QAMiner.mine` — deterministic-only mining over `claim_traces.json`.
4. `draft_response` + `response_agent_node` — personalisation (segment ->
   tone) + grounded drafting, using the GIVEN `KnowledgeBase`.
5. `eval_gate_node` — full-registry judgment on a candidate response.
6. `ImprovementCommandCenter._build_graph` — wire the 5 nodes into the
   one-cycle graph above.

## Discussion (bring back to the group)
- In testing, one of the 4 real goldens organically triggered the repair
  loop on its first live pass — not the hand-crafted demo, an actual
  customer response. What does it tell you that a CORRECT implementation
  can still trip its own gate on the first try?
- `capstone_selfcheck` never grades `relevance_judge`. Is there a
  deterministic proxy you could add that would catch SOME of what a human
  reviewer would catch, without needing another live call — or is that
  exactly the gap a subjective check exists to fill?
- `KnowledgeBase.retrieve` hard-filters by `policy_type`, which is why
  `policy_type_respected` can never fail on freshly-generated output. What
  OTHER check in this registry is still possible to fail even when every
  upstream component is working correctly — and what does that tell you
  about the difference between a bug and a genuine judgment call?
- This capstone processes each new golden through its own `graph.invoke()`
  call rather than looping customers inside one node. What would have to
  change about the state shape if analytics and mining needed to be
  per-customer instead of batch-level?
