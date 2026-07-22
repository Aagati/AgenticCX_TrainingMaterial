# PM · H3 — Retail: Assemble a CX Compliance Pack

**Track:** Retail | **Time box:** ~30 min | **Ships:** a compliance pack
**Pattern practiced:** consent capture, disclosure, PII/PCI redaction, retention, and deletion as one reusable module — **no API key needed**

## Scenario
Across the last three days you've built disclosure (Day 3, voice), memory
(Day 2), and guardrails (this morning). Today you package the compliance
side of all of that into one reusable `CompliancePack` any CX agent —
voice, chat, or email — can wrap itself in, rather than reimplementing
consent/disclosure/retention/deletion logic per channel.

## Your task
Build a `CompliancePack` class (or equivalent functions — your choice) with:
1. `disclose(customer_id) -> str` — returns a disclosure statement
   ("You're interacting with an automated assistant...") and logs that
   disclosure was given, with a timestamp, to `self.records[customer_id]`.
2. `capture_consent(customer_id, purpose, granted: bool)` — logs a consent
   record (purpose, granted, timestamp) for that customer. A customer can
   have multiple consent records for different purposes (e.g.
   "data_processing" vs. "marketing_contact").
3. `check_consent(customer_id, purpose) -> bool` — returns whether the
   MOST RECENT consent record for that customer+purpose was granted
   (a customer can change their mind — later records should override
   earlier ones for the same purpose).
4. `mask_pii_pci(text: str) -> str` — a standalone function that redacts
   card-number-like sequences (13-19 digits, optional spaces/dashes) to
   `"[CARD_REDACTED]"` and SSN-like sequences (`XXX-XX-XXXX`) to
   `"[GOVT_ID_REDACTED]"`.
5. `log_interaction(customer_id, raw_text)` — logs a free-text interaction
   record, but **always through `mask_pii_pci()` first**. This is the one
   place in the pack where arbitrary customer-typed text could reach
   storage, so redaction here is non-negotiable, not optional — the raw
   text must never be written, even transiently.
6. `apply_retention_policy(retention_days: int)` — removes any record (of
   any type) older than `retention_days` from `self.records`. Demonstrate
   this by inserting a fake old record with a backdated timestamp and
   confirming it gets purged while recent records survive.
7. `handle_deletion_request(customer_id)` — removes ALL records for that
   customer_id entirely (GDPR/DPDP-style right to erasure) and returns a
   confirmation.

Demonstrate the full lifecycle: disclose → capture two different consents
→ check both → change one consent → re-check → log two interactions
containing a fake card number and a fake SSN (confirm both come back
redacted, never raw) → apply retention (purge an old record) → handle a
deletion request → confirm the customer's records are gone.

## What "ships" means
A `CompliancePack` any of today's or earlier days' agents could import and
wrap themselves in — the same module handling a voice disclosure (Day 3),
a chat consent capture, or an email retention policy, because none of this
logic is channel-specific (same discipline as Day 2's channel adapters).

## Files
- `starter.py` — scaffold with TODOs. No mock data files needed.
- `solution.py` — reference solution.

## Setup
```bash
python starter.py
```
No API key needed — this lab is entirely deterministic record-keeping
logic, the same way this morning's guardrail functions were.

## Stretch goals
- Add a `export_for_subject_access_request(customer_id)` method that
  returns everything held about a customer in one structured response —
  the DPDP/GDPR "what do you have on me" request, distinct from deletion.
- Make retention period configurable per record TYPE (e.g. consent records
  retained longer than routine interaction logs).

## Discussion (bring back to the group)
- `check_consent` uses the MOST RECENT record. What's the risk of instead
  treating consent as a single boolean that just gets overwritten in
  place, with no history kept? (Hint: think about what a regulator or an
  auditor would ask for.)
