# Day 8 — CX Analytics, Personalisation & Continuous Improvement

Every Claude call in every lab is real — `ANTHROPIC_API_KEY` is assumed
configured (same repo-wide assumption every day makes). No other vendor
key is used this day.

Run from repo root: `.venv/Scripts/python.exe Day8/HandsOnExercise/<lab>/solution.py`

**Facilitator note — pacing.** Lab-1 and Lab-2 are the two labs to lead
live. Lab-1's new mechanic (Batches API submit/poll/parse) needs the most
narration — the batch call itself took ~3 minutes for 24 requests in
testing, budget for that dead air (or narrate the mechanism while it
runs). Lab-2 is the heaviest lab by topic count (7 of 12) and carries the
day's personalisation content — don't rush it. Lab-3 is the self-paced,
safe-to-skip assignment; if the cohort is short on time, cut it entirely
and go straight to the capstone, which explains Lab-3's one idea inline.
The capstone is designed for the 90%-likely case that nobody is
facilitating it live: it ships a self-check that grades the student's own
submission, so "did this work" doesn't require you to read their code.

---

## Lab-1 — Telecom: Conversation Analytics & Insights Pipeline
`Day8/HandsOnExercise/Lab1_Telecom_Conversation_Analytics/` · deterministic log stats + one Batches API job -> a 4-panel dashboard + a persistent run-history file

**Structure**
- `MetricsEngine` — six deterministic aggregations over `conversation_logs.json`
  alone (volume by channel/day/segment, containment rate, CSAT stats,
  repeat-contact rate). Zero model calls, zero cost.
- `InsightBatchExtractor` — builds 24 Batches API requests (one per
  conversation, forced tool use), submits as ONE job, polls
  `processing_status` to `"ended"`, parses results keyed by `custom_id`.
- `InsightAggregator` — sentiment/escalation/intent stats over the
  batch's output — everything here was unknowable before the batch ran.
- `Dashboard.build()` — matplotlib, 2x2 panel PNG.
- `append_run()` — persists one record to `analytics_runs.json` per run.

**Verified in testing (real API run)**
- 24/24 requests succeeded; batch took ~183s (~3 min) end to end.
- Deterministic metrics matched hand-verification exactly: containment_rate
  0.708 (17/24 resolved), csat average 3.56 (16/24 responded, distribution
  {"1":1,"2":3,"3":3,"4":4,"5":5}), repeat_contact_rate 0.2 (4/20 unique
  customers repeat: CUST-T01/T04/T07/T12).
- Real model run flagged 9 conversations `needs_escalation=true`, sentiment
  breakdown 13 positive / 3 neutral / 8 negative. This WILL vary run to
  run — don't let a student hardcode an expected count.

**Edge cases to cover**
- The batch call is genuinely slow relative to every other call in this
  curriculum — make sure students understand this is a deliberate
  cost/latency trade (50% cheaper per-token, no live customer waiting on
  it), not a bug in their polling loop.
- `MetricsEngine` and `InsightAggregator` are two separate classes on
  purpose — ask a student to explain why before they see the answer: one
  needs zero model calls, the other is impossible without one.
- Dashboard color rules: channel is categorical (fixed slot order), CSAT
  is sequential (light->dark = low->high), sentiment is diverging
  (negative/positive as true poles, neutral as the gray midpoint). A
  student who colors all four panels the same way missed the point of
  matching color job to data job.

---

## Lab-2 — Banking: Personalisation Engine + Continuous QA Loop
`Day8/HandsOnExercise/Lab2_Banking_Personalisation_QA_Loop/` · one registry, two jobs (mining historical failures, gating a live candidate) — the day's heaviest lab, 7 of 12 topics

**Structure**
- `PersonalisationEngine.rank_offers()` — hard-filters (segment, credit
  band, balance, already held, already declined), scores survivors
  (credit-tier + affordability + primary-fit bonus).
- QA check registry (`@register_check` / `run_all_checks`) — 3
  deterministic checks + 1 LLM-judge (`relevance_judge`, real haiku call).
- `TraceMiner.mine()` / `GoldenBuilder.promote()` — mine
  `banking_traces.json`, capture new failures to `goldens.json`.
- `eval_gated` — a decorator attaching `.run_gate()` to
  `generate_personalized_offer`, re-running it against every golden,
  logging a promote/reject verdict to `eval_runs.json`.
- New SDK surface: prompt caching (`cache_control` on the catalog
  reference block inside `draft_offer_message`).

**Verified in testing (real API run) — READ THIS BEFORE THE SESSION**
- `rank_offers` is fully deterministic and matched hand-verification
  exactly for all 10 customers (see `solution.py`'s trailing comment for
  the full table). `CUST-B04` and `CUST-B09` correctly resolve to ZERO
  eligible products — this is intentional, not a bug to fix.
- **Mining is NOT fully deterministic in this lab** — `TraceMiner.mine`
  runs the FULL registry (judge included) over the 13 historical traces.
  The 3 deterministic checks guarantee at least 6 failures (customers
  B01/B03/B04/B06/B07/B09). In testing, the real judge flagged TWO
  MORE (B05, B10), landing on 8/13 failing and 8 goldens captured.
  **Tell students not to expect exactly 6** — that surprised us in
  testing too, and it's the right prompt to have the "should mining use a
  judge at all" discussion (see the lab's README).
- **The eval gate can legitimately REJECT a correct implementation** — in
  testing, pass_rate landed at 0.875 (7/8) because one golden's
  `relevance_judge` disagreed with an otherwise fully compliant, fully
  eligible offer (all three deterministic checks passed). If a student's
  gate rejects, walk through the per-golden `checks` breakdown with them
  BEFORE assuming their code is wrong — a judge-only failure on an
  otherwise-clean offer is expected variance, not a bug.

**Edge cases to cover**
- `no_repeat_declined_pitch` is deliberately NOT a separate check —
  declined products are hard-excluded inside `rank_offers` itself, so
  `eligibility_respected` catches it for free. A student who adds a
  redundant fourth check isn't wrong, just duplicating coverage — good
  discussion prompt on where a business rule belongs.
- `CUST-B08` has TWO eligible products (`cashback_card` at 1.5,
  `starter_credit_builder` at 2.5) — the only customer where the
  primary-fit-bonus tie-break actually matters. Good one to trace by hand
  live.
- The prompt-caching block (`CATALOG_REFERENCE_BLOCK`) is below the real
  minimum token count for an actual cache write at this lab's toy catalog
  size — say this explicitly, don't let students think their cache is
  "broken" when nothing measurable changes; the mechanism is still 100%
  correctly wired.

---

## Lab-3 — Retail: Knowledge Management
`Day8/HandsOnExercise/Lab3_Retail_Knowledge_Management/` · relevance vs. trust, self-paced, safe to skip entirely

**Structure**
- `KnowledgeBase.retrieve()` — deterministic keyword/tag scoring, no
  notion of trust.
- `flag_staleness()` — two independent signals: explicit
  `status=="deprecated"`, or `last_updated` older than 365 days.
- `KnowledgeBase.retrieve_for_customer()` — personalisation boost +
  staleness flagging + ONE guarantee: the #1 slot is never a deprecated
  article when a named replacement exists.
- `draft_grounded_response()` — real sonnet call, grounded strictly in
  what survives retrieval.

**Verified in testing (real API run)**
- All three designed scenarios confirmed exactly as hand-verified:
  `CUST-R04` ("how do loyalty points work") — deprecated `ART-007` wins
  raw relevance (score 6 vs `ART-008`'s 5, because "points" is literally
  in the old title) and gets correctly auto-substituted.
  `CUST-R06` (holiday shipping) — `ART-014`/`ART-015` TIE at 9-9 (list
  order would silently favor the deprecated one) and get correctly
  resolved.
  `CUST-R05` (shipping cost) — the scope-boundary case: `ART-014` ties
  for 3rd place, stays flagged `"deprecated"` but UNSUBSTITUTED, because
  the guarantee only covers the #1 slot. All three are worth walking
  through live even in a self-paced setting, if you get 10 minutes.
- `max_tokens=400` on the drafting call — an earlier pass at 250 truncated
  two of six responses mid-sentence. If you see truncation with a
  student's version, that's the first thing to check.

**Edge cases to cover**
- This lab is explicitly safe to skip. Say so out loud — don't let a
  cohort burn facilitator-adjacent time here that the capstone doesn't
  need back.
- If you do run it live: ask students to predict, BEFORE running, whether
  `ART-007` or `ART-008` will rank first on pure keyword score. Almost
  everyone guesses wrong, which is the whole point.

---

## Capstone — Insurance: Prove the Loop Works Before a Real Customer Sees It
`Day8/HandsOnExercise/Capstone_Insurance_Improvement_Loop/` · every lab fused, self-graded via `capstone_selfcheck()`

**Structure**
- `KnowledgeBase` — GIVEN (Lab-3's idea, thinned) — see the capstone's own
  README for the given/build table and why the split is where it is.
- `AnalyticsEngine.compute()` / `Dashboard.build()` — Lab-1's pattern,
  batch-level, NOT a graph node (no per-item branching to justify one).
- QA registry / `QAMiner.mine()` / `GoldenBuilder.promote()` — Lab-2's
  pattern, with mining DELIBERATELY restricted to deterministic-only
  checks (a direct fix for the Lab-2 surprise above).
- `ImprovementCommandCenter._build_graph()` — 5-node LangGraph: response
  agent -> eval gate -> (promote | revise -> loops back to eval gate |
  reject).
- `capstone_selfcheck()` — the grading harness, given, not a TODO.

**Verified in testing (real API run) — this is the important one**
- `AnalyticsEngine`: 10 traces, `{"auto": 5, "home": 3, "health": 2}` —
  exact, deterministic, matches the hand-verified total every run.
- `QAMiner.mine` (deterministic-only): **exactly 5 of 10 traces fail,
  every single run** — `TR-I03`/`TR-I09` (wrong policy type),
  `TR-I04`/`TR-I10` (banned phrase), `TR-I05` (missing disclosure) -> 4
  unique customers (`CUST-C01/C03/C04/C05`). This is fully reproducible —
  unlike Lab-2, there is no judge-driven variance in mining here. If a
  student's mining doesn't produce exactly these 4, that's a real bug in
  their checks, not model variance.
- All 4 goldens PROMOTED on both test runs, all deterministic checks
  clean. One golden (`CUST-C04`) organically triggered the repair loop on
  its FIRST live pass in one run (not the hand-crafted demo — an actual
  generated response failed a check, got revised, passed on re-judgment)
  — a nice real-world proof the loop does something, if it happens during
  your session, call it out.
- `demo_repair_loop()`: hand-crafted draft containing two banned phrases
  ("guaranteed payout", "no questions asked") reliably fails first, gets
  revised, and — once the demo customer carries a real
  `pending_question` for the judge to evaluate against — reliably passes
  on re-judgment in testing. If it doesn't promote in a given run, that's
  the judge's real opinion on that specific rewrite, not a broken loop;
  either way `repair_attempted` should be `True` and the loop should not
  cycle a second time (there is no second retry path — confirm the cap).
- **`capstone_selfcheck()` gave an identical 6/6 PASS on a cold run
  (goldens.json didn't exist yet) and a warm run (goldens already
  captured, `run_cycle` skipped the graph entirely with a "no new
  goldens" message)** — confirming the self-check truly doesn't depend on
  file state. This is the property that makes it safe to use as a
  hands-off grading mechanism.

**Edge cases to cover**
- If a student's `run_cycle` is called twice in one session (e.g. they
  re-ran `python starter.py` without deleting `capstone_goldens.json`),
  the SECOND run will correctly report "no new goldens" and skip the
  graph — this is correct behavior, not a stuck script. `capstone_selfcheck`
  is what still validates their code in that state.
- `relevance_judge` is reported by the self-check but never hard-graded.
  If a student asks "why didn't my judge failure fail the grade" — that's
  the intended design, not a hole in the grading; walk through the
  Capstone README's discussion prompt on it.
- `KnowledgeBase.retrieve`'s hard policy-type filter means
  `policy_type_respected` cannot fail on freshly generated output BY
  CONSTRUCTION. If a student is confused why that check "never does
  anything" in the live cycle (only in mining, against old traces), that's
  correct — it's there to catch what the OLD system got wrong, and a
  correct new system structurally can't repeat that mistake.
