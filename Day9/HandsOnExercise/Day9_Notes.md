# Day 9 — Enterprise CX at Scale: CCaaS, Reliability, Advanced Guardrails & Safety

Every Claude call in every lab is real — `ANTHROPIC_API_KEY` is assumed
configured (same repo-wide assumption every day makes). No other vendor
key is used this day.

Run from repo root: `.venv/Scripts/python.exe Day9/HandsOnExercise/<lab>/solution.py`

**Facilitator note — pacing.** Lab-1 and Lab-2 are the two labs to lead
live. Lab-1's retry backoff really sleeps (jitter, a few seconds total
across the run) — narrate it as deliberate dead air, not a bug. Lab-2 is
the heaviest lab by topic count (5 of 12) and its three paired requests
(REQ-009/010, REQ-011/012, REQ-013/014) are the moments to slow down for.
Lab-3 is self-paced and safe to skip; if the cohort is short on time, cut
it and go straight to the Capstone, which ships AND enforces its one idea.
The Capstone is designed for the 90%-likely case that nobody is
facilitating it live: 14 self-check assertions, all deterministic, and
independently confirmed identical on both a cold run and a warm run in
testing. Budget for the Capstone's Batches job — observed ~2.5-3 minutes
for 10 requests in testing, in the same range as Day 8 Lab-1's ~3 minutes
for 24, so Batches latency isn't purely proportional to request count at
this scale; narrate the mechanism while it runs.

**A model-behavior note that affects every lab this day:** `claude-sonnet-5`
reasons by default. Left alone, a chunk of `max_tokens` goes to an
invisible thinking pass before any visible text is written — in early
testing this actually tripped `generation_terminated_cleanly`-style checks
on perfectly ordinary requests at `max_tokens=300`. Every drafting call in
every lab and the Capstone now passes `thinking={"type": "disabled"}`
explicitly. If a student's own draft calls omit this and hit mysterious
truncation, this is the first thing to check.

---

## Lab-1 — Telecom: Contact Center Resilience
`Day9/HandsOnExercise/Lab1_Telecom_Contact_Center_Resilience/` · one
simulated shift, 18 contacts -> a deterministic reliability report + a
persistent run-history file

**Structure**
- `CircuitBreaker` — three states, injected clock (`t` in seconds, never
  `time.time()`), transition log.
- `ResilientCaller.call_with_retry` (given the name in starter, no class
  wrapper needed in practice) — full jitter, per-attempt classification.
- `guarded_downstream_call` — breaker OUTSIDE, retry INSIDE, wrapping
  `CoreStatusAPI.check`.
- `classify_contact` — the one model judgment; degrades to `"degraded":
  True` rather than raising; deliberately NOT used to gate the handoff
  branch (system state decides that, not the model's opinion).
- `QueueRouter.select_queue` / `CapacityGovernor.admit` — deterministic
  skill-based routing with real concurrency limits per queue.
- `draft_holding_message` — three cost tiers (template/haiku/sonnet).
- `WarmHandoffPackager.build` — model writes the one-sentence prose;
  system attaches the facts.

**Verified in testing (real API run) — identical across two runs**
- Breaker transitions: `closed→open@t=75`, `open→half_open@t=170`,
  `half_open→closed@t=170`. Final state `closed`, `consecutive_failures=0`
  (two later clean calls, CT-017/CT-018, reset the streak after CT-013/
  CT-016 had ticked it back up to 2 — a real, reproducible property of a
  pure consecutive-failure counter, not a bug).
- Total physical attempts against `CoreStatusAPI`: **25**.
- Short-circuited (zero physical attempts): 5 contacts, `CT-007`–`CT-011`
  (all arrive inside the open window).
- Contacts that shed at least one hop: 4 (`CT-006` sheds to overflow;
  `CT-013` sheds one hop into `Q-TECH-2`; `CT-014`/`CT-016` shed two hops
  into overflow). `CT-017`/`CT-018` arrive LATER and are admitted into
  `Q-TECH-1` directly (hops=0) — capacity isn't a ratchet, slots free up.
- Handoff/self-serve split: 11 handoff (4 unassigned — `CT-006`, `CT-010`,
  `CT-014`, `CT-016` — because `HA-104` is the only escalation-skilled
  agent and is offline) / 7 self-serve (5 haiku, 2 sonnet — the two
  premium contacts, `CUST-TC12` and `CUST-TC05`'s repeat contact, are
  exactly the two that land self-serve with a clean downstream).
- `classify_contact`'s urgency/needs_human/summary: real haiku judgment,
  reported in every record, never gates a branch. This WILL vary run to
  run — don't let a student hardcode it.

**Edge cases to cover**
- `CT-011` is short-circuited on the downstream call AND still admitted
  into `Q-TECH-1` directly — two independent systems, two independent
  verdicts on the same contact. Ask a student to predict this before
  running; most predict the queue is also "down."
- `guarded_downstream_call`'s composition order (breaker outside, retry
  inside) is the single most common inversion. If a student's breaker
  trips on ONE flaky call instead of three, they've swapped the layers.
- `demo_degraded_classification()` exists because no live contact in this
  fixture happens to trip `classify_contact`'s own except-branch — the
  free template tier is real code, exercised only by the demo.

---

## Lab-2 — Insurance: The Guardrail Stack
`Day9/HandsOnExercise/Lab2_Insurance_Guardrail_Stack/` · nine layers, three
verdicts, one hash-chained log — the day's heaviest lab by topic count

**Structure**
- Eight `@register_guardrail` layers across input/permission/output/
  compliance; layer 90 (`audit_chain_write`) is `always_runs=True`.
- `GuardrailStack.evaluate` — short-circuits on BLOCK, transforms on
  REDACT, runs the audit layer regardless.
- `HashChainedAuditLog.append`/`.verify`.
- `draft_claim_response` — prompt caching on the jurisdiction rulebook
  (Day 8's mechanic, reused), thinking disabled.
- `handle_request`/`run_corpus` — two-sided scoring.

**Verified in testing (real API run) — identical across two runs**
- **Exactly 7 of 16 requests BLOCK**: `REQ-002` (injection),
  `REQ-003` (authority claim), `REQ-004` (rbac_action_allowed — tier1
  attempting `issue_payout`), `REQ-005` (rbac_scope_and_authority —
  claims_adjuster's $5,000 ceiling), `REQ-006` (scope — customer not in
  actor's book), `REQ-007` (injection variant), `REQ-013`
  (prohibited_claim, NY). **Zero missed blocks, zero false blocks, zero
  wrong-layer verdicts.**
- The three named pairs all confirmed exactly as designed: `REQ-009`
  (CA, redacts — appends disclosure + written-confirmation sentence) vs
  `REQ-010` (TX, same amount, no redaction — disclosure already present,
  under threshold); `REQ-011` (tier1, policy number masked) vs `REQ-012`
  (fraud_investigator, same number unmasked); `REQ-013` (NY, blocks on the
  finality phrase) vs `REQ-014` (TX, same phrase, passes — TX doesn't
  prohibit it).
- Bonus pair `REQ-005`/`REQ-008`: the identical $8,000 payout blocks for
  `claims_adjuster` (ceiling $5,000) and passes for `senior_adjuster`
  (ceiling $15,000).
- Audit chain: **26 entries** after one run — the 6 requests blocked at
  input/permission each write 1 entry (6 total); the 9 that pass cleanly
  each write 2 entries, one per phase (18 total); `REQ-013` passes
  input/permission then blocks at compliance, writing 2 entries (the
  remaining 2). 6+18+2=26. `verify()` -> `(True, None)`.

**Edge cases to cover**
- Ask BEFORE running: "should the audit layer run when layer 10 blocked?"
  Then show `always_runs=True`.
- `CUST-IN08`'s jurisdiction (`"MA"`) isn't in `jurisdiction_rules.json` —
  falling back to `DEFAULT` is correct; a `KeyError` is the bug.
- `_canonical` is given for a reason: a student who re-serializes with
  default `json.dumps` gets an intermittently-failing `verify()`.
- **A real bug found during testing, worth walking through live:** the
  first draft of the corpus assigned each trace's `precomposed_response`/
  actor combination without re-checking each request against its intended
  actor — three requests silently exercised the WRONG actor's role. The
  fix was in the fixture, not the code, and it's a good live demonstration
  of why hand-verifying expected corpus outcomes on paper (or by running
  and diffing) matters before trusting a "looks right" fixture.

---

## Lab-3 — Retail: Redaction at the Persistence Boundary
`Day9/HandsOnExercise/Lab3_Retail_Log_Redaction/` · one contained idea,
self-paced, safe to skip entirely

**Structure**
- `redact` — five ordered patterns, findings without the matched text.
- `write_trace` — recursive redaction at the ONE write path.
- `response_leak_check` — the outbound direction; reports, never rewrites.
- `draft_support_reply`, `verify_log_clean` — given.

**Verified in testing (real API run)**
- 7 of 12 transcripts clean (`TR-R02/05/06/07/08/10/12`); 5 carry findings
  (`TR-R01` card, `TR-R03` card-with-spaces, `TR-R04` govt_id+phone,
  `TR-R09` email, `TR-R11` api_key).
- `TR-R07`'s `ORD-4532110288219901` correctly survives un-redacted (the
  negative-lookbehind + `\b` combination works).
- `TR-R05`'s card, split across two turns, is correctly NOT caught —
  expected, documented, not a bug.
- `verify_log_clean()` -> `True` on the written log every run.
- `demo_response_leak()`'s hand-crafted leaking reply is correctly caught
  (`safe=False`) — no live draft in this fixture happens to leak another
  customer's email on its own.

**A real regex bug found and fixed during testing, worth telling students
about even in a self-paced lab:** the first version of the `card_number`
pattern used a plain negative lookbehind for `"ORD-"`. It failed —
`ORD-4532110288219901` still got redacted, because the regex engine simply
started its match one digit later (`532110288219901`, still 15 digits,
no longer preceded by `"ORD-"`) and the lookbehind never got a chance to
reject it. The fix was adding a leading `\b`: inside a contiguous run of
digits there is no word boundary, so the engine can no longer start the
match anywhere except the true beginning of the run, where the lookbehind
correctly fires. **This is exactly the kind of "looks like a secret, isn't"
case the lab's own README calls out** — it just happened to be a bug in the
lab's reference implementation before it became the lab's own worked
example.

**Edge cases to cover**
- Say out loud that this lab is safe to skip.
- If run live, ask students to predict whether `TR-R07`'s order number
  survives before they see the fix.
- A student who returns the matched text in `findings` has written a
  second copy of the secret — the most common miss in review.

---

## Capstone — Banking: Enterprise Won't Trust a Demo
`Day9/HandsOnExercise/Capstone_Banking_Enterprise_Trust/` · every lab
fused, plus four named threads from Days 4/5/8, self-graded via
`capstone_selfcheck()`

**Structure**
Seven-node graph (`intake → agent → guardrail → {release|handoff|repair|
deny}`, `repair → guardrail` the one cycle, `deny → handoff` never a dead
end); five thinned guardrails + given audit layer; `CircuitBreaker` +
`guarded_action` wrapping `CoreBankingAPI`; `AuditChain`; `CapacityMeter` +
`Dashboard`; `run_corpus` (deterministic, batch); `BatchGate` + `eval_gated`
(real Batches API); `capstone_selfcheck`; five `demo_*` functions.

**Verified in testing (real API run) — this is the important one**
- **Corpus: exactly 8 of 20 traces BLOCK** (`AC-002/003/004/006/008/011/
  018/019`), **zero missed blocks, zero false blocks, zero wrong-layer
  verdicts** — fully reproducible, no judge involved in this corpus at all.
- **Live pipeline, all 10 customers**: 7 `released`, 3 `routed_to_human` —
  `CUST-BK05` (tier1 exceeds the $1,000 ceiling at $1,500),
  `CUST-BK08` (fraud_investigator can't `issue_provisional_credit` at
  all), `CUST-BK09` (a fully CLEAN pass, routed anyway because $12,500
  exceeds the agent card's $10,000 `approval_threshold` — the
  executable-governance-pack proof).
- `CapacityMeter`: `NY=4/CA=3/TX=3`, `guardrail_pass_rate=0.8`,
  `approved=True`.
- **Breaker demo**: opens after exactly 3 consecutive failures; the three
  failing calls consume **9** physical attempts (3 retries each,
  `fail_always`); the 4th call, arriving while still inside the recovery
  window, costs **zero** physical attempts.
- **Idempotent replay**: two calls to `guarded_action` with the same
  dispute_id and idempotency_key produce **1** physical attempt and **1**
  ledger row — Day 4's replay contract, now proven under a breaker that
  can actually fail.
- **Audit chain**: `verify()` -> `(True, None)` on the freshly-written
  chain; a tampered entry is caught at its exact index, and "fixing" that
  entry's own hash just moves the break one entry forward (its neighbor's
  `prev_hash` is unchanged) — the same two-step demo as Lab-2's.
- **`capstone_selfcheck()` gave an identical 14/14 PASS on a cold run
  (no runtime files) and a warm run (files already present)** — confirming
  the self-check doesn't depend on accumulated file state, the same
  property Day 8's Notes singled out as what makes a self-check safe as a
  hands-off grading mechanism.
- `BatchGate`'s `batch_judge_pass_rate` (informational, never graded):
  observed 0.5 on one run and 0.6 on another over the same 10 responses —
  real judge variance. Don't let a student treat this number as a target;
  the deterministic `pass_rate` (always 1.0 in testing) is what's graded.

**Edge cases to cover**
- If a student's self-check fails the idempotent-replay assertion but
  passes the breaker-traversal one, they're probably generating a FRESH
  idempotency key per retry attempt inside `call_with_retry` instead of
  reusing the dispute's own key — exactly the Day-4 bug the key exists to
  prevent.
- The second router (deny-before-generation) is new relative to Day 8. A
  student who moves the RBAC check inside `agent_node` still passes most
  self-check items but pays for a model call on every denied request —
  walk the cost, not just the test result.
- `capstone_selfcheck` never grades the compliance judge — same design as
  Day 8, same answer if a student asks why.
- This capstone has no `GoldenBuilder`/mining step, unlike Day 8's. That's
  a deliberate simplification (the corpus is hand-labeled, not mined from
  ambiguous history) — see the Capstone's own README for the fuller
  explanation if a student pushes on it.
