# PM · H4 — Retail: Capstone — Personalised Outbound Journey Agent

**Track:** Retail | **This is the fusion lab** — every gate and specialist from PM_H1-H3, one LangGraph, plus personalisation

## Mental model: a graph, not a pipeline

The previous three labs each made ONE decision per stage, function-call
style. This capstone wires the same decisions into an actual multi-agent
**graph** (LangGraph `StateGraph`) — a supervisor-style conditional router
delegating to whichever specialist agent the situation calls for, with
one genuine loop where a specialist revises its own output:

```
customer_id
   │
   ▼
ConsentGate node        (H3)  — allowed at all? which channel?
   │ blocked → END
   ▼
EligibilityEngine node   (H1)  — frequency cap, quiet hours
   │ blocked → END
   ▼
supervisor router: at_risk_churn?
   │                              │
   no                            yes
   │                              ▼
   │                     EscalationAgent (H2's HandoffPackager) → END
   ▼
TieringAgent            (H1)  — cheap classify → bespoke draft OR template
                                  (persona (H2) + offer (NEW) combined)
   ▼
ComplianceAgent         (H3)  — passes?
   │ pass                         │ fail
   ▼                              ▼
SendAgent → END              RepairAgent (H3) ──loops back to── ComplianceAgent
                                              │ fails AGAIN → END (blocked_safety)
```

Five stop points, five distinct outcomes a customer can land on:
`blocked_consent`, `blocked_eligibility`, `escalated`, `blocked_safety`,
`sent`. Every real pipeline like this has more ways to NOT send a message
than ways to send one — that asymmetry is normal, not a bug.

## Why this is "multi-agent," not just branching code

Day2's `PM_H1` built a supervisor that delegates to specialists through
its own tool-use loop. Day6's `PM_H2` built a 2-node LangGraph with a
confirm-gate. This capstone combines both lessons: gate NODES (no model
call needed) feed a supervisor-style conditional router
(`_route_after_eligibility`) that hands off to one of three roles —
`EscalationAgent`, `TieringAgent`, or the `ComplianceAgent`/`RepairAgent`
pair. That last pair is the one thing a flat function-call chain can't
express cleanly: **a loop**, where a specialist's output gets judged,
handed to another specialist for revision, and judged again — the system
correcting its own work against feedback, not just executing a fixed
sequence once.

## What's actually NEW here (vs. H1-H3)

**Personalisation** — the piece none of the first three labs built. It's
a two-key lookup: `segment → offer` (retail_offer_catalog.json) crossed
with `locale → persona` (H2's pattern). The offer a customer sees and the
voice it's delivered in are two independent axes, both data-driven, both
swappable without touching code.

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
| Any `blocked_safety` surviving the repair attempt | The message TYPE needs a template, not more retries — see PM_H3 |
| `sent` tier split (`high` vs `low`) | How much of your campaign spend is going to bespoke drafting vs. free templates — the tiering ROI number |

## When to reach for the fully-fused pattern

Not every outbound use case needs all five gates. Build up to this
incrementally:
- Just sending reminders, single language, single segment? You need
  `EligibilityEngine` alone (PM_H1).
- Multi-language, multi-channel journeys with escalation? Add
  `LanguageRouter` + `JourneyMemoryStore` + `HandoffPackager` (PM_H2).
- Regulated content, real compliance exposure? Add `ConsentGate` +
  `BrandSafetyLinter` (PM_H3).
- All of the above, at once, with real personalisation? This lab.

## Files
- `retail_offer_catalog.json` — segment→offer mapping, channel tiers/quiet
  hours, banned phrases, required disclosure, baseline conversion rates.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv langgraph
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- This graph checks gates in a fixed order (consent → eligibility →
  churn-risk router → tiering → compliance). Is there a case where
  reordering matters — where checking eligibility before consent, say,
  would change the RIGHT answer, not just the audit trail's shape?
- The repair loop caps itself at ONE retry via `repair_attempted`. What
  would happen without that cap, and what's the right number of retries
  in a real system — is it a fixed count, a cost budget, or something
  else entirely?
- Every gate/agent here is per-customer, per-campaign-run. What would need
  to change to make `analytics_log` and `JourneyMemoryStore` durable
  across campaign runs (a real datastore instead of an in-memory
  list/dict, a real checkpointer instead of no persistence between
  `graph.invoke()` calls), and who in an org would actually consume that
  data day to day?
