# Day 7 — Proactive, Outbound & Multilingual CX Agents

Every Claude call in every lab is real — `ANTHROPIC_API_KEY` is assumed
configured (same repo-wide assumption every day makes). No other vendor
key is used this day; there's no real-if-key/simulated-fallback branching
because there's no optional external vendor to fall back from.

Run from repo root: `.venv/Scripts/python.exe Day7/HandsOnExercise/<lab>/solution.py`

**Facilitator note — pacing.** PM_H1 and PM_H2 are the two labs to lead
live — they're the richest and carry the most new mechanics per minute
(cost/channel tiering in H1; cross-channel memory + locale persona +
hand-off in H2). PM_H3 is the self-paced assignment: its TODOs are almost
entirely deterministic Python (JSON lookups, conditionals) rather than
prompt-engineering judgment calls, so it's debuggable against the printed
"Expected" trace without a facilitator interpreting model behavior live.
PM_H4 is the capstone — assign it AFTER H1-H3 have landed, not as first
exposure; it fuses every primitive from the first three labs and is, by
construction, the densest thing built this day.

---

## PM·H1 — Banking: Outbound & Proactive Orchestration
`Day7/HandsOnExercise/PM_H1_banking_outbound_proactive/` · eligibility gate → cheap-model tier classification → templated or bespoke draft → channel-tiered send → simulated A/B uplift

**Structure**
- `EligibilityEngine.filter_eligible()` — trigger match, per-channel
  consent, frequency cap, and timezone-aware quiet hours, all
  deterministic.
- `classify_urgency()` — real haiku call, forced tool use, decides
  "high"/"low" per eligible customer.
- `draft_message()` (sonnet, "high" only) vs. `template_message()` (zero
  tokens, "low") — the cost-tiering payoff.
- `OutboundOrchestrator.run_campaign()` — wires the above, appends a
  structured event to `analytics_log`.
- `ProactiveValueMeter.measure_uplift()` — simulates a contacted cohort
  against a control cohort from `campaign_policies.json`'s baseline rates.

**Test matrix**

| # | Trigger | Eligible | Notes |
|---|---|---|---|
| 1 | `payment_due_soon` | CUST-001, CUST-005, CUST-010 | CUST-001/005 have a tight balance-vs-due-date — expect "high"/sonnet. CUST-010 has the same due date but a $5,000 balance — expect "low"/template. Classification is a REAL model call; don't assume the bucket, check `model_used` in the log. |
| 2 | `payment_due_soon` blocked | CUST-003 (email quiet hours), CUST-007 (no consent on any channel), CUST-009 (sms quiet hours), CUST-004/CUST-006 (trigger doesn't match — due date too far out) | Five distinct exclusion reasons, one customer each |
| 3 | `fraud_alert` | CUST-008 | Expect "high" (fraud + real drafting) |
| 4 | `fraud_alert` blocked | CUST-002 | Frequency cap — contacted 1 day ago |

**Edge cases to cover**
- Quiet-hours math wraps midnight (`[21, 8]` means quiet 9pm-8am) — verify
  `in_quiet_hours()` against a window that does NOT wrap (e.g. hypothetical
  `[9, 17]`) as a sanity check students can reason through by hand.
- A customer failing more than one eligibility check at once — confirm
  the implementation doesn't need to report ALL failing reasons, just
  correctly exclude them; useful discussion prompt if a student asks "which
  reason actually applied."
- `ProactiveValueMeter`'s uplift numbers are seeded (`seed=7`) — same
  trigger, same customer set, reproducible uplift across runs, even though
  the classification calls upstream are real and can vary in wording.

---

## PM·H2 — Telecom: Multilingual Journeys, Personas & Hand-off
`Day7/HandsOnExercise/PM_H2_telecom_multilingual_journey/` · one customer, two touches, two channels, one memory store

**Structure**
- `LanguageRouter.route()` — locale → language/tone/disclosure bundle
  from `locale_policies.json`, falls back to en-US on an unknown locale.
- `JourneyMemoryStore` — facts keyed on `customer_id`, independent of
  channel.
- `JourneyOrchestrator.advance_turn()` — real sonnet call, forced tool
  use, folds in persona + accumulated memory, returns
  stage/reply/fact.
- `HandoffPackager.build_handoff()` — real sonnet call, ALWAYS English
  output regardless of the journey's language.

**Test matrix**

| # | Sequence | Expected |
|---|---|---|
| 1 | LanguageRouter across all 5 locales | Distinct language/tone/disclosure per locale, straight from the JSON — no hardcoded per-language branching in code |
| 2 | CUST-J1, ja-JP, chat turn 1 (router disconnects nightly) | `stage="diagnosing"`, a fact captured about the recurring outage |
| 3 | CUST-J1, ja-JP, voice turn 2 (next day, already tried power-cycle + cable swap, explicitly requests escalation) | `memory.get_facts()` has turn 1's fact available BEFORE this call runs (check this explicitly); `stage` should land on `"escalate"` given the strengthened signal, though this is a real model judgment call |
| 4 | Hand-off bundle | Always English, even though the entire journey was conducted in Japanese — this is the point of a SEPARATE summarization call, not a forwarded transcript |
| 5 | CUST-J2, de-DE, single-touch data-balance question | No account-lookup tool exists in this lab — expect the model to ask a clarifying question or explain it needs account access, not fabricate a number |

**Edge cases to cover**
- If a run's `stage` doesn't land on `"escalate"` for turn 2 (real model
  variance), the solution still demos the hand-off bundle anyway, labeled
  accordingly — confirm students understand WHY (a capability demo
  shouldn't be gated on a coin flip the lab can't fully control).
- An unknown locale code — confirm `LanguageRouter.route()` falls back to
  en-US rather than crashing mid-journey.
- Ask students explicitly: what belongs in `JourneyMemoryStore` vs. what
  doesn't (see the README's table) — a common mistake is capturing small
  talk or already-resolved details as if they were durable facts.

---

## PM·H3 — Insurance: Consent, Compliance & Brand Safety
`Day7/HandsOnExercise/PM_H3_insurance_consent_safety/` · two deterministic gates + one repair loop, self-paced

**Structure**
- `ConsentGate.check()` — do-not-contact, per-channel opt-in, consent
  freshness (`consent_freshness_days`), each an independent check.
- `BrandSafetyLinter.check()` — banned-phrase substring match + verbatim
  required-disclosure check.
- `draft_outbound_message()` / `repair_message()` — real sonnet calls;
  the linter checks the OUTPUT of both, never trusts the prompt alone.
- `SafetyRailPipeline.send()` — composes both gates + one repair attempt,
  logs every outcome.

**Test matrix**

| # | Customer/channel | Expected |
|---|---|---|
| 1 | CUST-101/sms | Allowed — fresh consent, opted in |
| 2 | CUST-102/sms | Blocked `not_opted_in_sms` |
| 3 | CUST-103/email | Blocked `consent_stale` (captured 2024-05-01, >365 days before NOW=2026-08-03) |
| 4 | CUST-104/voice | Blocked `do_not_contact` |
| 5 | CUST-999/sms | Blocked `no_consent_record` — not in the registry at all |
| 6 | Hand-crafted bad draft ("...guaranteed payout, no questions asked!") | Trips BOTH `banned_phrase_violations` (two phrases) and `missing_disclosure` |
| 7 | `SafetyRailPipeline` full run, 5 cases | CUST-102/104 never reach drafting (consent-blocked first — cheapest possible failure); CUST-101/103/105 reach a real sonnet draft, expected to pass the linter on the first try |

**Edge cases to cover**
- The adversarial brand-safety case is HAND-CRAFTED, not real model
  output — the real drafting calls are expected to pass clean. Make sure
  students understand the repair loop exists for the case that doesn't
  happen in this lab's demo, not that it's untested — it's exercised
  deterministically via the hand-crafted string instead.
- Consent freshness is checked with a fixed reference date
  (`NOW = date(2026, 8, 3)`) — changing that date changes which customers
  are "stale," a good live-tweak to show the freshness window in action.
- Discuss: substring matching misses paraphrases ("basically guaranteed"
  doesn't trip "guaranteed payout") — this is a DELIBERATE simplicity
  trade-off (fast, deterministic, auditable), not an oversight; see the
  README's discussion prompt.

---

## PM·H4 — Retail: Capstone — Personalised Outbound Journey Agent
`Day7/HandsOnExercise/PM_H4_retail_capstone_journey/` · every H1-H3 gate/specialist fused into ONE LangGraph multi-agent graph, plus segment→offer personalisation

**Structure**
- `ConsentGate` / `EligibilityEngine` / `BrandSafetyLinter` — thinned
  reimplementations of H3/H1/H3's gates (not cross-imports), wrapped as
  graph NODES (`_consent_node`, `_eligibility_node`).
- `LanguageRouter` / `JourneyMemoryStore` / `HandoffPackager` — H2's
  routing, memory, and hand-off, same shape; hand-off lives inside
  `_escalation_agent`.
- `classify_tier()` + `draft_personalized_offer()` / `template_offer_message()`
  — H1's cost-tiering, retargeted to "does this case earn a bespoke
  message," crossed with locale persona AND segment-based offer
  (`retail_offer_catalog.json`); lives inside `_tiering_agent`.
- `PersonalizedOutboundJourneyAgent._build_graph()` — the multi-agent
  fusion: a LangGraph `StateGraph` with 8 nodes, a supervisor-style
  conditional router (`_route_after_eligibility`) delegating to
  `escalation_agent` or `tiering_agent`, and a genuine LOOP
  (`repair_agent` -> `compliance_agent` -> re-judge) — the one piece of
  agentic behavior a flat function-call chain (which is what this file
  used to be, before this retrofit) can't express.
- `demo_pm_recap()` — standalone, cheap rerun of one deterministic concept
  from each of H1/H2/H3, no dependency on those labs having executed.
- **This cohort doesn't get H3** — `_compliance_agent` /
  `_route_after_compliance` / `_repair_agent` (the H3-derived brand-safety
  loop) ship as GIVEN, fully-implemented code in `starter.py`, not a TODO;
  students only build `_escalation_agent`, `_tiering_agent`, `_send_agent`,
  and `_build_graph` (TODO 1-4), plus an optional bonus TODO 5
  (`advance_customer_clocks`, the multi-touch demo below). The README/code
  docstrings for this lab are also scrubbed of "(H1)"/"(H2)"/"(H3)"
  pointers for the same reason and carry a self-contained Concept
  Cheatsheet instead — this facilitator doc is the one place that still
  names the source labs, since you're presumably running the full
  curriculum.

**Facilitator note — why this is a graph, not a pipeline.** An earlier
draft of this lab was a flat method (`run_customer()`) calling each
primitive in sequence — functionally identical output, but NOT
multi-agent, just branching Python. It was rebuilt as a LangGraph
`StateGraph` specifically so the capstone would compound on Day2's
supervisor+specialist pattern and Day6 PM_H2's graph pattern, per the
day's brief that Day7 should read as advanced multi-agent orchestration,
not a bigger if/else chain. Worth surfacing this explicitly if a student
asks "why not just a function" — the answer is the repair loop: a graph
can express "specialist A's output gets judged, sent to specialist B for
revision, and judged again" as actual topology (a cycle), where a
function chain would need a hand-rolled while-loop that doesn't compose
the same way once you add a third or fourth revision path.

**Test matrix**

| # | Customer | Expected outcome |
|---|---|---|
| 1 | RET-01 (en-US, loyalty_gold, sms consent, local hour 8 — not quiet) | `sent` via sms |
| 2 | RET-02 (es-MX, sms consent, local hour 7 — INSIDE sms quiet window) | `blocked_eligibility` / `quiet_hours` |
| 3 | RET-03 (ja-JP, `at_risk_churn=True`, passes consent+eligibility) | `escalated` — never reaches drafting at all |
| 4 | RET-04 (sms consent False, email consent True, local hour 8 — not in email's quiet window) | `sent` via email — the `pick_channel()` fallback in action |
| 5 | RET-05 (`do_not_contact=True`) | `blocked_consent`, regardless of anything else about their profile |

**Edge cases to cover**
- RET-03's `at_risk_churn` check happens AFTER consent+eligibility but
  BEFORE any drafting call — confirm students see that ordering and can
  explain why (spending zero drafting tokens on a customer who's about to
  be blocked anyway, but still routing the ones who pass straight to a
  human rather than a template).
- None of the 5 demo customers trip `BrandSafetyLinter` on real model
  output, so the `repair_agent` <-> `compliance_agent` loop isn't
  exercised in the campaign run — it's exercised deterministically via
  `demo_pm_recap()`'s hand-crafted adversarial string instead.
  `repair_attempted` caps the loop at exactly one retry — a good
  live-break exercise is removing that cap and showing the graph would
  otherwise cycle forever on a message type that can never satisfy the
  linter.
- `ProactiveValueMeter` here only has ONE trigger (`win_back`) in its
  baseline-rates fixture — a good stretch exercise is adding a second
  trigger and confirming the meter generalizes without code changes.
- Ask students to trace the OUTCOME MIX (see the README's table) across
  the 5 demo customers — 2 sent, 1 escalated, 2 blocked (one per gate) —
  and connect each outcome type to the organizational question it answers
  (consent hygiene vs. scheduling vs. working-as-intended vs.
  compliance). Classification is a REAL model call; don't assume the
  tier split — check `model_used` in the log rather than hardcoding an
  expected "1 high / 1 low," same caveat as PM_H1's `classify_urgency`.
- `JourneyMemoryStore` is disk-backed (`campaign_memory.json`, gitignored,
  regenerated/grown on every run) — but the base single-touch demo alone
  never proves this is load-bearing, since a fact written on the way to a
  send is only ever read AFTER it's written, in the same touch. The bonus
  section (touch 2, ten days later, same memory store) is what actually
  demonstrates a LATER decision reading an EARLIER touch's history — and
  the closing "fresh `JourneyMemoryStore()`" reload proves the facts
  survive independent of the `agent` object, not just across touches in
  one process.
