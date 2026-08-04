# PM · H4 — Retail: Capstone — Personalised Outbound Journey Agent

**Track:** Retail | **This is the fusion lab** — every gate and specialist a regulated outbound-messaging system needs, one LangGraph, plus personalisation

## Mental model: a graph, not a pipeline

An outbound campaign has to answer, per customer: can we contact them at
all (consent), should we contact them right now (eligibility), does their
case need a human or a bespoke message, and is whatever we're about to
send actually safe to send. This capstone wires all of that into an
actual multi-agent **graph** (LangGraph `StateGraph`) — a supervisor-style
conditional router delegating to whichever specialist agent the situation
calls for, with one genuine loop where a specialist revises its own
output:

```
customer_id
   │
   ▼
ConsentGate node        — allowed at all? which channel?
   │ blocked → END
   ▼
EligibilityEngine node   — frequency cap, quiet hours
   │ blocked → END
   ▼
supervisor router: at_risk_churn?
   │                              │
   no                            yes
   │                              ▼
   │                     EscalationAgent (hands off to a human) → END
   ▼
TieringAgent            — cheap classify → bespoke draft OR template
                           (persona + offer + prior contact history combined)
   ▼
ComplianceAgent         — passes?
   │ pass                         │ fail
   ▼                              ▼
SendAgent → END              RepairAgent ──loops back to── ComplianceAgent
                                              │ fails AGAIN → END (blocked_safety)
```

Five stop points, five distinct outcomes a customer can land on:
`blocked_consent`, `blocked_eligibility`, `escalated`, `blocked_safety`,
`sent`. Every real pipeline like this has more ways to NOT send a message
than ways to send one — that asymmetry is normal, not a bug.

## Why this is "multi-agent," not just branching code

Two GATE nodes (deterministic, no model call needed) feed a
supervisor-style conditional router (`_route_after_eligibility`) that
hands off to one of two roles — `EscalationAgent` or `TieringAgent` — and,
after drafting, a second router (`_route_after_compliance`) hands off
between the `ComplianceAgent`/`RepairAgent` pair. That pair is the one
thing a flat function-call chain can't express cleanly: **a loop**, where
a specialist's output gets judged, handed to another specialist for
revision, and judged again — the system correcting its own work against
feedback, not just executing a fixed sequence once.

## What's actually NEW here

**Personalisation** — a two-key lookup: `segment → offer`
(retail_offer_catalog.json) crossed with `locale → persona`. The offer a
customer sees and the voice it's delivered in are two independent axes,
both data-driven, both swappable without touching code.

**Persistent, cross-touch memory** — `JourneyMemoryStore` is disk-backed
(`campaign_memory.json`). A fact written when a customer is sent an offer
(or escalated) is still there the next time this script runs, days or
weeks later — the tiering/drafting specialist reads it back before
deciding what to say, and the drafter is instructed not to repeat an
identical pitch. The bonus section at the bottom of `solution.py` /
`starter.py` runs a SECOND campaign touch, ten days after the first,
against the same memory store, to prove this actually happens rather than
just being wired and never exercised.

## Why `at_risk_churn` short-circuits BEFORE drafting

A customer flagged as likely to leave is exactly the customer an
automated, generic offer is most likely to backfire on — they need a
human who can actually negotiate, not a templated 15%-off message. The
check sits right after eligibility and before ANY drafting: the cost of
routing to a human here is one Claude call (the hand-off summary), not
zero, but it's a much better trade than sending a message that reads as
"they didn't even notice I'm about to leave."

## Reading the outcome mix

| Outcome | What it tells you |
|---|---|
| High proportion `blocked_consent` | Your contactable audience is shrinking — a data/consent-hygiene problem, not a campaign problem |
| High proportion `blocked_eligibility` | Your dispatch TIME is misaligned with your audience's timezones — a scheduling problem |
| Any `escalated` | Working as intended — these are exactly the cases that shouldn't be automated |
| Any `blocked_safety` surviving the repair attempt | The message TYPE needs a template, not more retries |
| `sent` tier split (`high` vs `low`) | How much of your campaign spend is going to bespoke drafting vs. free templates — the tiering ROI number. This is a REAL model classification each run, not a fixed split — don't hardcode an expected count |

## Concept Cheatsheet

Every mechanic this capstone uses, explained on its own — no need to have
seen any other lab first.

| Concept | What it does |
|---|---|
| **ConsentGate** | Deterministic, no model call. Checks do-not-contact and "is there ANY opted-in channel" — blocks BEFORE any generation happens, because there's no point drafting a message you're not allowed to send. |
| **EligibilityEngine** | Deterministic. Frequency cap (don't contact someone too soon after the last touch) + timezone-aware quiet hours (`in_quiet_hours` wraps midnight when the window's start > end, e.g. `[21, 8]` means quiet from 9pm to 8am in the CUSTOMER's local time). |
| **LanguageRouter / persona** | One data lookup (`locale → language + tone`) — a Japanese-locale customer gets a more formal register than a US one, same underlying agent. No per-language if/elif in code; a new locale is a new dict entry. |
| **Cost-tiered classify → draft** | A cheap model (haiku) makes a real, forced-tool-use classification: does this case earn a bespoke message ("high") or is a zero-token template enough ("low")? Only the "high" bucket pays for a capable model (sonnet) to draft. |
| **BrandSafetyLinter + repair loop** | Deterministic post-generation check — banned phrases (substring match) + a required disclosure that must appear VERBATIM. Runs on the model's OUTPUT, never trusts the system prompt alone. On failure, one repair attempt (rewrite against the SPECIFIC violations) is re-checked; a second failure blocks rather than retrying forever — that cap is what keeps the loop from cycling indefinitely on a message type that can never pass. |
| **JourneyMemoryStore (persistent)** | Facts keyed on `customer_id`, independent of channel. Disk-backed (`campaign_memory.json`) so a customer's history survives past the current process — a LATER campaign touch, even in a brand-new run of the script, reads it back. |
| **HandoffPackager** | A human retention specialist may not read the customer's language — this call always writes its summary in English, and is a SEPARATE call from the customer-facing conversation, not a forwarded transcript. |
| **ProactiveValueMeter** | Simulates a contacted cohort against a held-out control cohort using `retail_offer_catalog.json`'s baseline conversion rates, so "measuring proactive value" produces an actual number instead of a claim. |

## When to reach for the fully-fused pattern

Not every outbound use case needs all five gates. Build up to this
incrementally:
- Just sending reminders, single language, single segment? You need
  `EligibilityEngine` alone.
- Multi-language, multi-channel journeys with escalation? Add
  `LanguageRouter` + `JourneyMemoryStore` + `HandoffPackager`.
- Regulated content, real compliance exposure? Add `ConsentGate` +
  `BrandSafetyLinter`.
- All of the above, at once, with real personalisation and memory that
  persists across touches? This lab.

## Files
- `retail_offer_catalog.json` — segment→offer mapping, channel tiers/quiet
  hours, banned phrases, required disclosure, baseline conversion rates.
- `campaign_memory.json` — created at runtime by `JourneyMemoryStore.persist()`;
  not checked into the repo, regenerated (and grown) every time the script
  runs. Delete it to reset to a cold start.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv langgraph
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## What you'll build (starter.py)
The consent/eligibility gates and the compliance/repair loop are given,
fully implemented. You'll build:
1. `_escalation_agent` — hand off to a human, and log the escalation to
   memory.
2. `_tiering_agent` — classify + draft/template, informed by this
   customer's prior contact history.
3. `_send_agent` — log the send to memory.
4. `_build_graph` — wire all 8 nodes together.
5. `advance_customer_clocks` (**bonus, optional**) — the day-advance logic
   that drives the second campaign touch at the bottom of the demo.
   Everything above it runs and prints correctly without this one; leaving
   it unimplemented just skips the bonus touch-2 section with a one-line
   notice instead of running it.

## Discussion (bring back to the group)
- This graph checks gates in a fixed order (consent → eligibility →
  churn-risk router → tiering → compliance). Is there a case where
  reordering matters — where checking eligibility before consent, say,
  would change the RIGHT answer, not just the audit trail's shape?
- The repair loop caps itself at ONE retry via `repair_attempted`. What
  would happen without that cap, and what's the right number of retries
  in a real system — is it a fixed count, a cost budget, or something
  else entirely?
- `JourneyMemoryStore` now persists to `campaign_memory.json`;
  `analytics_log` still doesn't — it's rebuilt from scratch every run.
  Why was a flat JSON file enough for one and not the other? Think about
  single-writer per-customer append vs. multi-writer, queryable, retained
  analytics — and who in an org would actually consume each one day to
  day.
