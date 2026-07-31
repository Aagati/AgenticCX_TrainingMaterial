# Day 5 · Post-Lunch Lab H1 (Banking) — Governance Pack Template

Fill in every blank below. This is what you'd hand to a compliance reviewer before a release.

## 1. Agent Card
A one-page spec of what the agent is. Be specific enough that someone who has never seen your project could understand its scope and limits.

- **Agent name & one-line purpose:** _(what is this agent for, in one sentence?)_
- **Scope — what it IS allowed to do:** _(list the intents/tasks in scope)_
- **Scope — what it is NOT allowed to do:** _(list explicit out-of-scope actions — these should route to a human)_
- **Autonomy level (L0–L3, from Topic 5):** _(state the level and the oversight mechanism that matches it)_
- **Data the agent touches:** _(e.g. account numbers, transaction history, contact details — be exhaustive)_
- **Known limitations:** _(where does it currently fail or need a human? Be honest — this protects you later)_

## 2. Audit Trail Schema
Define what gets logged for every action the agent takes. At minimum, include the fields below — add any others your agent needs.

| Field | What you'll log here |
|---|---|
| `timestamp` | |
| `action` | |
| `inputs` | |
| `outcome` | |
| `autonomy_level_at_time` | |
| _(add your own)_ | |

## 3. Disclosure Statement
The exact wording a customer would see or hear at the start of a conversation — satisfying the EU AI Act's transparency requirement that people be told they're interacting with AI.

> _(write the exact customer-facing sentence(s) here)_

## 4. Consent Record
What data use are you asking consent for, and how is that consent captured and stored?

- **What the customer is consenting to:**
- **How consent is captured** (e.g. explicit opt-in at conversation start):
- **How long the record is retained, and where:**

---

## Appendix — Worked Example (Reference Only)
This is a filled-in example for a **different** agent (an insurance claims-status bot), to show the level of detail expected. Do not copy it — your banking agent's answers will be different.

### 1. Agent Card (example)
- **Agent name & one-line purpose:** ClaimStatusBot — answers policyholder questions about the status of an existing insurance claim.
- **Scope — what it IS allowed to do:** Look up claim status; explain claim stages; send a copy of the policy document; retry a failed premium payment.
- **Scope — what it is NOT allowed to do:** File a new claim; cancel a policy; change coverage; discuss claim details before identity verification.
- **Autonomy level:** L2 — acts autonomously within the scope above; a human reviews a random 10% audit sample weekly.
- **Data the agent touches:** Policy number, claim number, claim status history, payment method on file (masked), contact email.
- **Known limitations:** Struggles with multi-claim households; cannot explain claim denials in detail (routes to a human for that).

### 2. Audit Trail Schema (example)
`timestamp`, `action` (e.g. `get_claim_status`), `inputs` (claim number, masked policy ID), `outcome` (success/fail + summary), `autonomy_level_at_time`, `human_reviewed` (bool).

### 3. Disclosure Statement (example)
> "You're chatting with our virtual claims assistant, which uses AI to help answer your questions. You can ask to speak with a human at any time."

### 4. Consent Record (example)
Consent requested: use of claim and policy data to answer the customer's question in this session. Captured via an explicit "I agree" button before the chat begins. Retained for 90 days, tied to the session ID, per the DPDP data-minimisation principle.
