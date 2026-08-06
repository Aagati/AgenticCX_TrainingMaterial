# Capstone: Banking - Enterprise Won't Trust a Demo

**Track:** Banking | **This is the fusion lab** — every mechanic from Lab-1/
Lab-2/Lab-3, plus four named mechanics compounded forward from Days 4, 5 and 8

Banking has never carried a capstone in this curriculum before (Days 1-8
used Telecom / Insurance / Retail / Insurance for their capstone-equivalents)
— fitting, since "enterprise at scale" is exactly the banking-disputes shape:
high volume, strict RBAC, hard-money ceilings, and a regulator who will ask
for the audit trail.

## Read this first if you never got to Lab-3

Lab-3 was this day's self-paced lab. There's a real chance you're reading
this having never opened it. That's fine by design — `redact_for_log` below
ships complete, and unlike Day 8's capstone (which merely *explained* its
skipped lab's idea inline), this one actually **enforces** it:
`capstone_selfcheck` asserts the redaction is still wired up, because a
redaction bug in an enterprise pipeline is a breach, not a stale citation.

## Mental model: a graph, but only where it earns it

```
adversarial_corpus.json (20 traces)         banking_customers.json (10 disputes)
        │                                            │
        ▼                                            ▼
   run_corpus()                          for each customer:
   (deterministic, batch,           ┌─────────────────────────────┐
    NO graph needed)                │  intake_node                 │
                                     │  (input+permission groups)   │
                                     │       │proceed      │deny    │
                                     │       ▼             ▼        │
                                     │  agent_node      deny_node   │
                                     │  (guarded_action              │
                                     │   + draft_response)           │
                                     │       │                       │
                                     │       ▼                       │
                                     │  guardrail_node ◄──────┐      │
                                     │  (compliance group)     │      │
                                     │   │pass    │fail        │      │
                                     │   ▼         ▼           │      │
                                     │ release/  repair ───────┘      │
                                     │ handoff   (once)                │
                                     └─────────────────────────────┘
                                                  │
                                                  ▼
                                    CapacityMeter + Dashboard
                                                  │
                                                  ▼
                            eval_gated: BatchGate judges every response
```

`run_corpus` is straight-line batch Python — 20 traces, one pass, no
per-item branching to justify a graph. The per-customer cycle is different:
there are TWO decision points (deny-before-generation, and judge/repair/
re-judge), and one of them is a genuine cycle. That's what a LangGraph buys
here that a flat function chain can't express as cleanly.

## Given vs. build, and why the split is where it is

| Given | Build | Why |
|---|---|---|
| `redact_for_log` | — | Lab-3's idea — the lab most likely to have been skipped |
| `CoreBankingAPI` (the simulated core + its fault schedule + the idempotency ledger) | `CircuitBreaker`, `call_with_retry`, `guarded_action` | The fault injector isn't yours to control; the resilience primitives **are** Lab-1 |
| `@register_guardrail` registry, audit layer's write path, `AuditChain` file I/O + `_canonical` | The 5 guardrails, `GuardrailStack.evaluate`, `AuditChain.append`/`.verify` | The registry is Lab-2's pattern; what gets registered and the chain math are yours to prove again |
| `Dashboard.build` | `CapacityMeter.compute` | Chart-drawing is repeated boilerplate; the metrics **are** Lab-1's topic |
| `intake_node`, `repair_node`, `release_node`, `handoff_node`, `deny_node` | `agent_node`, `guardrail_node`, `_build_graph` | The repair loop's mechanics aren't new this day; the guarded action + the stack are exactly Lab-1 and Lab-2 |
| `BatchGate` submit/poll plumbing, `eval_gated` | `BatchGate.build_requests`/`.run`, `run_corpus` | Batches submit/poll was **Day 8 Lab-1's** teaching point, not this day's |
| `capstone_selfcheck`, all five `demo_*` | — | Grading harness isn't yours to edit |

**The split rule, extended one clause beyond Day 8's:** *"If a piece tests
something Lab-1 or Lab-2 actually walked you through live, it's a TODO. If
it's Lab-3's territory, or infrastructure that was never this day's
teaching point, it's given — or was a **prior day's** teaching point that
this capstone only reuses, given, with a pointer back to where it was
taught."* That clause is what puts Batches submit/poll on the given side
without pretending it's trivial — Day 8 already spent a whole lab on it.

## What this compounds from earlier days

No earlier capstone in this curriculum reached back past its own day. This
one does, on four named threads:

| # | Prior-day artifact | What it did then | What this capstone does with it | The new lesson |
|---|---|---|---|---|
| 1 | Day 4's idempotent, audited action (`process_refund` / `create_ticket`, keyed by `idempotency_key`) | A safe, audited action. The key existed *in case of* a retry; nothing in Day 4 ever retried. | `CoreBankingAPI.issue_provisional_credit`, identical replay semantics, wrapped in `guarded_action`'s `CircuitBreaker` + retry. `core_banking_faults.json` makes it actually fail. | **Idempotency and retry are one design decision, not two.** `demo_idempotent_replay` calls the same dispute twice and the ledger stays at one row. |
| 2 | Day 4's per-user permission check (`check_permission`'s "doesn't own it" branch) | Per-**user** permission on one resource. | `rbac_action_allowed` + `rbac_credit_ceiling` over `banking_policy_pack.json["roles"]` — role → capability, plus a numeric ceiling Day 4 had no analogue for. | **Role→capability is what an org chart maps onto.** `demo_rbac_deny` shows the identical request denied for one role and released for another. |
| 3 | Day 5's governance pack (agent card, audit trail schema) and ROI floor-gate | A reviewable **document**. The audit trail was a schema on paper. | `banking_policy_pack.json["agent_card"]["approval_threshold"]` is **enforced at runtime** — it's what routes `CUST-BK09` to a human even on a clean pass. `AuditChain` writes the same field set, hash-chained, on disk. `CapacityMeter`'s floor gate recasts the ROI logic: don't approve on volume alone if the safety floor is failing. | **The governance pack stops being a document and starts being a policy the code obeys.** |
| 4 | Day 8's Batches API (Lab-1) + `eval_gated` decorator (Lab-2) | Batch-scored an analytics transcript; gated a personalisation offer, one failure direction. | `BatchGate` submits every processed response as ONE Batches job for a compliance judge; `.run_gate()` re-runs the whole pipeline. | **The gate is two-sided here** — `run_corpus` already proved zero missed AND zero false blocks before the eval gate even runs. |

## Why this capstone's mining step looks different from Day 8's

Day 8's capstone mined *historical* traces to discover which ones already
violated policy, then promoted the failures into goldens. This capstone's
`adversarial_corpus.json` is hand-authored with KNOWN correct labels
(`expected_verdict`, `expected_blocking_layer`) rather than mined from
ambiguous history — so there's no separate `GoldenBuilder` step here.
`eval_gated`'s `.run_gate()` re-runs the LIVE pipeline against deterministic
expectations directly (every customer NOT expected to be denied should
release or hand off; every customer expected to be denied should be).
That's a deliberate simplification, not a missing feature: this pipeline
doesn't have a "yesterday's bad traces" dataset the way a QA/personalisation
loop does, so there's nothing to mine.

## `capstone_selfcheck()` — fourteen assertions, all deterministic

Hard-asserted, identical on a cold run and a fiftieth run: the corpus blocks
exactly the expected 8/20 traces with zero false and zero missed blocks;
the breaker opens after exactly 3 consecutive failures and makes zero
physical attempts while open; an idempotent replay produces one ledger row
from two calls; the audit chain verifies clean and correctly flags a
tampered entry at its exact index; the graph wires `deny -> handoff`; RBAC
denies the same request for one role and releases it for another; and
`CUST-BK09`'s $12,500 dispute — over the agent card's `approval_threshold`
— routes to a human even on an otherwise-clean pass. The compliance judge's
opinion (`batch_judge_pass_rate`) is printed but never graded, exactly Day
8's `eval_gated` philosophy applied one level up.

## Files
- `banking_policy_pack.json` — the agent card, 3 roles (`tier1_support`,
  `senior_adjuster`, `fraud_investigator`), 3 actors, NY/CA/TX + DEFAULT
  jurisdiction rules.
- `banking_customers.json` — 10 customers, NY=4/CA=3/TX=3, including the
  CA/TX same-amount pair (`CUST-BK02`/`CUST-BK04`) and the over-threshold
  customer (`CUST-BK09`).
- `core_banking_faults.json` — fault schedule (by dispute_id) for the 8
  disputes that reach the resilient action.
- `adversarial_corpus.json` — 20 traces, 8 adversarial, covering every
  guardrail layer.
- `capstone_audit_chain.json` / `capstone_eval_runs.json` /
  `capstone_dashboard.png` — created at runtime; gitignored. Delete any of
  them to reset.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv matplotlib langgraph
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## What you'll build (starter.py)
1. Five guardrail layers (`injection_probe`, `rbac_action_allowed`,
   `rbac_credit_ceiling`, `jurisdiction_disclosure_present`,
   `prohibited_claim`) — the registry and audit layer are given.
2. `GuardrailStack.evaluate` — the ordered chain.
3. `CircuitBreaker`, `call_with_retry`, `guarded_action` — thinned from Lab-1.
4. `AuditChain.append`/`.verify` — same hash-chain math as Lab-2.
5. `draft_response` — grounded strictly in what the action actually returned.
6. `agent_node`, `guardrail_node`, `_build_graph` — the two TODO nodes and
   the topology.
7. `CapacityMeter.compute` — the batch metrics feeding the dashboard.
8. `run_corpus`, `BatchGate.build_requests`/`.run` — the deterministic
   corpus test and the Batches-API judge.

## Discussion (bring back to the group)
- `CUST-BK09` gets handed to a human on a *clean* pass, purely because a
  JSON field said so. Who is allowed to change that field, and what stops
  the change from shipping without a review?
- `demo_idempotent_replay` proves one dispute called twice produces one
  ledger row. What happens to that guarantee if two DIFFERENT dispute IDs
  are accidentally assigned the same idempotency key upstream?
- `intake_node` can deny before a single token is generated. What class of
  guardrail *cannot* be moved before generation, and what does that cost
  per blocked request if it isn't?
- This capstone has no golden-mining step, unlike Day 8's. Is that a real
  simplification, or does it just mean this pipeline hasn't been in
  production long enough yet to have a "yesterday's bad traces" file?
- `capstone_selfcheck` never grades the compliance judge. Is there a
  deterministic proxy that would catch some of what a human reviewer
  catches, or is that exactly the gap a subjective check exists to fill?
