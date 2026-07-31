# Day 5 · Post-Lunch Lab H3 (Team Exercise) — Capstone Brief Template

One page. Specific enough that your team could start building tomorrow.

## 1. Problem
- **Who is the customer, and what are they trying to do?:**
- **Why does this currently need a human?:**

## 2. Channels
- **Which single channel are you starting with?:** _(e.g. chat only, to start — resist the urge to include voice AND chat on day one)_

## 3. Success Metrics
Numbers, not ranges. A metric you can't gate on isn't finished.

- **Target resolution rate:**
- **Target CSAT:**
- **Target cost per contact:**

## 4. Eval Plan
- **How many golden conversations, covering which intents?:**
- **What will your LLM-as-judge rubric check?:**
- **What are your eval-gate thresholds (reuse this afternoon's gate logic)?:**

---

## Appendix — Worked Example (Reference Only)
A filled-in example for a telecom billing-dispute agent, to show the level of specificity expected — not the topic to copy.

### 1. Problem (example)
Postpaid mobile customers who see an unexpected charge on their bill currently have to call support and wait an average of 14 minutes to get an explanation, even though 60% of these charges are one of three well-understood reasons (roaming, a plan change mid-cycle, or a one-time add-on).

### 2. Channels (example)
Chat only, embedded in the billing section of the mobile app.

### 3. Success Metrics (example)
Resolution rate ≥ 70% (of the three known charge types); CSAT ≥ 4.2/5; cost per contact ≤ $0.90 blended.

### 4. Eval Plan (example)
15 golden conversations covering the 3 known charge types plus 5 out-of-scope edge cases. LLM-as-judge rubric checks: correct charge explanation, no policy overreach (no promises of a refund without human approval), and a clear next step for the customer. Eval gate: block release if resolution < 70% on goldens, or if the judge finds any unauthorised refund promise.
