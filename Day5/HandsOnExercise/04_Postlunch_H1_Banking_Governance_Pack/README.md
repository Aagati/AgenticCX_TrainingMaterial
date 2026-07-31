# Post-Lunch · H1 — Banking: Governance Pack

**Track:** Banking | **Time box:** 35–45 min | **Ships:** a completed governance pack, specific enough for a compliance sign-off
**Pattern practiced:** turning an agent's scope/autonomy/data footprint into reviewable, non-code artifacts

## Objective
Using the banking agent from this morning's H2 Online QA lab (or your own capstone agent idea, if further along) as the subject, complete all four sections of the governance pack template: **Agent Card**, **Audit Trail Schema**, **Disclosure Statement**, and **Consent Record**.

## Steps
1. Open `Governance_Pack_Template.md` and read the worked example in the Appendix first — it shows the level of specificity expected (it is a **different** agent, not the one you're documenting, so don't copy it directly).
2. Complete the Agent Card: purpose, scope, autonomy level (use the L0–L3 scale from the morning's Governance topic), data touched, and known limitations.
3. Design the Audit Trail Schema: list the fields your system would log for every action the agent takes (at minimum: timestamp, action, inputs, outcome, autonomy level at time of action).
4. Draft the Disclosure Statement: the exact wording a customer would see or hear at the start of a conversation, satisfying the EU AI Act's transparency expectation.
5. Draft the Consent Record structure: what data use are you asking consent for, and how is that consent captured and stored (DPDP-aligned)?
6. Swap your draft with another pair. Would their governance pack be enough for you, as a reviewer, to sign off on a release?

## What "ships" means
A completed `Governance_Pack_Template.md` — all four sections filled in for your chosen agent, specific enough that a compliance reviewer unfamiliar with the project could understand what the agent does and doesn't do.

## Files
- `Governance_Pack_Template.md` — the fill-in template. Complete the four numbered sections; leave the Appendix worked example as reference only.
- `agent_card_schema.py` — **supplementary, added after reviewer feedback.** A typed (Pydantic) version of Section 1's Agent Card, so it can be validated in CI/CD and rendered to markdown automatically. The markdown template above is still the primary deliverable — compliance/legal reviewers who don't read code need a document they can open and comment on directly. Requires `pip install pydantic`; run with `python agent_card_schema.py`.

## Facilitator tips
- This lab is intentionally the most "paperwork-heavy" of the day. Frame it early as what actually unlocks a production release, not a bureaucratic add-on — that framing changes how seriously participants take the wording.
- Watch for autonomy levels that don't match the actions described — e.g. an "L1: human approves every action" agent card paired with an audit trail that has no approval-timestamp field.

## Discussion (bring back to the group)
If your agent's autonomy level were raised from L1 to L2 tomorrow, which single field in your audit trail schema would matter most, and why?
