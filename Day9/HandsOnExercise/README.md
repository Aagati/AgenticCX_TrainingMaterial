# Day 9 — Enterprise CX at Scale: CCaaS, Reliability, Advanced Guardrails & Safety

Four labs, same shape Day 7 established and Day 8 refined: **Lab-1 and
Lab-2 are the compounded, facilitator-led labs** (the two richest, densest
in new mechanics), **Lab-3 is self-paced and deliberately lightweight**
(safe to skip entirely — nothing downstream depends on it), and the
**Capstone** fuses everything into one LangGraph, tested by its own
built-in self-check. **New this day: the Capstone also reaches back past
its own day** — it explicitly advances four named mechanics from Days 4, 5
and 8, which no prior capstone in this curriculum has done.

Every lab assumes `ANTHROPIC_API_KEY` is configured — Day 9 is Claude-only,
same convention every prior day held. `langgraph` is a real dependency only
in the Capstone (the LangGraph `StateGraph`); `matplotlib` is only needed
there too (the one dashboard this day builds).

Run from repo root: `.venv/Scripts/python.exe Day9/HandsOnExercise/<lab>/solution.py`

---

## Labs

| Folder | Lab | Industry | Facilitator pacing | Topics covered |
|---|---|---|---|---|
| `Lab1_Telecom_Contact_Center_Resilience` | The Call Center Falls Over the Moment It Gets Popular | Telecom | **Led live** | CCaaS integration, Routing & handoff, Reliability at scale, Resilience engineering, Cost & capacity |
| `Lab2_Insurance_Guardrail_Stack` | One Guardrail Isn't a Guardrail Stack | Insurance | **Led live** | Advanced guardrails, Guardrail stack, Identity & permissions, Compliance at scale, Audit & governance |
| `Lab3_Retail_Log_Redaction` | The Transcript Log Is Leaking Card Numbers | Retail | Self-paced, safe to skip | Security |
| `Capstone_Banking_Enterprise_Trust` | Enterprise Won't Trust a Demo | Banking | Capstone (combine-all, self-graded) | Every topic above, fused — plus four named mechanics compounded from Days 4, 5 and 8 |

## Why Security ended up alone in Lab-3

Day 9's twelve topics cluster into exactly two mechanisms and one leftover.
*A contact under load* is one mechanism — CCaaS integration, routing &
handoff, reliability at scale, resilience engineering, and cost/capacity
are all the same simulated shift seen from five angles, which is why Lab-1
carries five of them without feeling like five labs. *A request under
scrutiny* is the other — advanced guardrails, the guardrail stack, identity
& permissions, compliance at scale, and audit & governance are all one
pipeline, which is why Lab-2 carries the other five.

Security is the leftover, and it's the leftover for a good reason: it's
the only topic on the list whose core mechanic — deterministic redaction
at the persistence boundary — needs no orchestration, no identity model,
and no reliability primitives to be correct. That makes it the only topic
that can survive being skipped. Folding it into Lab-2 would have turned a
five-topic lab into a six-topic lab and buried the one idea on this list a
junior engineer can act on tomorrow morning without changing anything
about their architecture.

One difference from Day 8's treatment of its at-risk slot: Day 8's capstone
*explained* Lab-3's idea inline. Day 9's capstone *enforces* it —
`redact_for_log` ships as given code and `capstone_selfcheck` asserts
against it, because a redaction bug in an enterprise pipeline is a breach,
not a stale citation.

(On "Cost & capacity" and "Capacity & cost": the source topic list names
both. They're one cluster and Lab-1 covers them as one — the cost of a
contact and the capacity to serve it are the same decision, made at the
same moment, by the same governor.)

## What compounds into what

The Capstone doesn't cross-import Lab1-3's code — it re-implements a thin,
banking-flavored version of each primitive, the same "compound, don't
cross-import" rule Day 7's and Day 8's capstones followed:

- `redact_for_log` — Lab-3's idea, thinned to the two critical patterns,
  shipped as GIVEN code (not a TODO) specifically because Lab-3 is the lab
  most likely to have been skipped — and additionally *enforced* by the
  self-check, so deleting it fails the grade.
- `CircuitBreaker` / `call_with_retry` / `guarded_action` — Lab-1's
  reliability primitives, re-pointed at a core-banking credit action
  instead of a telecom status API.
- The guardrail registry, `GuardrailStack.evaluate`, `AuditChain` — Lab-2's
  stack, thinned from nine layers to six and re-keyed to banking
  jurisdictions and banking roles.
- `CapacityMeter` / `Dashboard` — Lab-1's cost/capacity telemetry,
  promoted to this day's one matplotlib chart, with a floor-gate panel
  Lab-1's own report never needed.
- A LangGraph `StateGraph` for the two parts that are genuinely per-request
  and branching — deny-before-generation, and draft → judge → (if it
  fails) repair and judge again — wiring the guarded action and the stack
  into actual graph edges rather than a hand-rolled while-loop.

## What compounds from earlier days

**New this day** — Day 7's and Day 8's capstones fused within their own
day. This one also reaches back:

1. Day 4's idempotent, audited action (safe ticketing/refund actions,
   keyed by `idempotency_key`) → the Capstone's `CoreBankingAPI` +
   `guarded_action` — the SAME replay contract, now actually retried under
   a circuit breaker.
2. Day 4's per-user permission check (the "doesn't own it" branch) →
   generalized into role → capability (`rbac_action_allowed`) plus a
   numeric ceiling Day 4 had no analogue for (`rbac_credit_ceiling`).
3. Day 5's governance pack (agent card, audit trail schema) and ROI
   floor-gate → runtime policy: `AGENT_CARD["approval_threshold"]` actually
   routes traffic, and `AuditChain` is hash-chained instead of a flat list.
4. Day 8's Batches API (Lab-1) + `eval_gated` decorator (Lab-2) →
   `BatchGate` judges every processed response as one Batches job;
   `.run_gate()` re-runs the whole pipeline with a SECOND failure
   direction Day 8's gate never had.

See the Capstone's own README for the full table with exact prior-day
paths and function names.

## New this day: SDK surface and production patterns

| What | Where | Why it's new |
|---|---|---|
| `Anthropic(max_retries=, timeout=)` | Lab-1 | First time this curriculum turns the SDK's own retry loop **down** rather than accepting the default — so a lab's own retry logic is what a student actually observes |
| Explicit `APIStatusError` / `APITimeoutError` / `RateLimitError` handling | Lab-1 | Failure becomes a named, catchable branch instead of an uncaught traceback |
| **`stop_reason` as a guardrail signal** (`refusal`, `max_tokens`) | Lab-2 | The model ships a safety layer of its own; the stack has to record when it fires — and a truncated response is a compliance failure here, not a cosmetic one, since the disclosure is the last sentence |
| **`thinking={"type": "disabled"}`** | Lab-1, Lab-2, Lab-3, Capstone | `claude-sonnet-5` reasons by default — left on, it silently eats the `max_tokens` budget before any visible text is written. Every short, policy-constrained drafting call this day disables it explicitly |
| **Hand-rolled circuit breaker** (closed / open / half-open) | Lab-1, Capstone | The one reliability primitive the SDK does *not* provide, with an injected clock so a time-dependent state machine is reproducible in a report |
| **Ordered guardrail pipeline with three verdicts** (PASS / BLOCK / **REDACT**) | Lab-2, Capstone | Chain-of-responsibility: BLOCK terminates, REDACT *transforms and continues* — the difference between a stack and a list of booleans |
| **Hash-chained audit log** | Lab-2, Capstone | Tamper-**evident** by construction — advances Day 4's and Day 5's flat append-only lists for the cost of one sha256 per entry |
| **Role-based access control** (role → capability, not user → resource) | Lab-2, Capstone | Generalizes Day 4's per-user ownership check into something an org chart maps onto |
| **Jurisdiction-keyed compliance table** | Lab-2, Capstone | The same sentence can be legal in one state and illegal in another — one lookup, not one branch per state |
| **Deterministic skill-based routing + a real capacity governor** | Lab-1 | Advances Day 2's supervisor→specialist routing into the queue/concurrency model a real contact center runs |
| **Two-sided guardrail scoring** (missed blocks *and* false blocks) | Lab-2, Capstone | A guardrail stack that's only graded on catches can ship a stack nobody can actually use |

## Persistent memory, every lab

| Lab | File | What it holds |
|---|---|---|
| `Lab1` | `resilience_runs.json` | One record per simulated shift: breaker transitions, routing/shed counts, outcome and cost-tier mix |
| `Lab2` | `guardrail_audit_log.json` | Every request's per-layer verdict trail, hash-chained — the chain *is* the memory, and it's the only Day-9 file whose integrity is itself asserted |
| `Lab3` | `redacted_trace_log.json` | Every transcript written through the redaction boundary, plus findings by pattern and severity |
| `Capstone` | `capstone_audit_chain.json` / `capstone_eval_runs.json` | The hash chain, and every eval-gate verdict (deterministic pass rate + the batch judge's informational opinion) |

All of these are gitignored and created at runtime — delete any of them to
reset that lab to a cold start. `capstone_selfcheck()` gives the same
verdict either way, by design (verified cold and warm during testing).

## Running the labs

Each lab folder has a `starter.py` (TODOs to fill in) and a `solution.py`
(reference, runs end-to-end).

```bash
cd Lab1_Telecom_Contact_Center_Resilience
python starter.py       # participant version
python solution.py      # reference — runs end-to-end
```

**Setup, all labs:**
```bash
pip install anthropic pydantic python-dotenv matplotlib langgraph
export ANTHROPIC_API_KEY=sk-ant-...
```

## How each lab ties back to the day's topics

- **Lab-1 Telecom** → CCaaS integration, Routing & handoff, Reliability at
  scale, Resilience engineering, Cost & capacity
- **Lab-2 Insurance** → Advanced guardrails, Guardrail stack, Identity &
  permissions, Compliance at scale, Audit & governance
- **Lab-3 Retail** → Security
- **Capstone Banking** → Every topic above, fused into one graph, tested by
  its own self-check — plus four named mechanics compounded from Days 4, 5
  and 8

See `Day9_Notes.md` for the full facilitator test-matrix/edge-case
companion, in the same format as `Day8_Notes.md`.
