# PM · H3 — Insurance: Consent, Compliance & Brand Safety

**Track:** Insurance | **Industry angle:** renewal reminders and claim-status updates fired outbound, not requested

## Mental model: two gates, two different jobs

```
                 BEFORE generation                 AFTER generation
                 ──────────────────                ─────────────────
customer_id  →   ConsentGate.check()      draft  →  BrandSafetyLinter.check()
                 "am I ALLOWED to          text      "is the TEXT itself
                  contact this person       ↓          safe to send?"
                  right now?"              (repair
                       │                    once if
                  allowed?                  needed)
                  ┌────┴────┐                   │
                 no        yes                passed?
                  │          │              ┌────┴────┐
              blocked    generate          no        yes
             (0 tokens     draft            │          │
              spent)                    blocked     SENT
                                        (even after
                                          1 repair)
```

Two gates, not one, because they answer two unrelated questions. Consent
is about the PERSON (did they agree to be contacted, on this channel,
recently enough). Brand safety is about the MESSAGE (does this specific
text make a claim the company can't back, or omit required wording). A
customer can fail consent and pass brand safety trivially (the message was
never written), or pass consent and fail brand safety (they said yes to
being contacted, the model still wrote something reckless).

## Why consent is checked BEFORE generation, not after

There's no live turn to ask "can I record this?" inside — the ENTIRE
interaction is the outbound send. If you generate first and check consent
after, you've already spent a model call (and, worse, already composed a
message) for someone you had no standing to contact. The gate has to be
the very first thing that runs.

## Consent freshness — the angle this lab adds beyond capture/lifecycle

Capturing consent once isn't permanent permission. A checklist for "is
this consent still good":

| Check | Question |
|---|---|
| Exists at all | Is there a record for this customer? |
| Do-not-contact | Did they ask to be left alone entirely, overriding any channel opt-in? |
| Channel-specific | Did they opt in on THIS channel — sms consent ≠ voice consent ≠ email consent |
| Freshness | Was consent captured recently enough (`consent_freshness_days`), or does it need to be reconfirmed? |

Each is an independent failure mode — log which ONE applied, don't
collapse them into a single "not allowed" boolean, or you can't answer
"why didn't we contact this customer" six months later.

## Brand safety = substring checks, not vibes

The linter here is two mechanical checks:
1. **Banned phrases** — case-insensitive substring match against a policy
   list (`"guaranteed payout"`, `"risk-free"`, ...).
2. **Required disclosure, verbatim** — must appear WORD FOR WORD, not
   paraphrased. A model that captures the meaning but changes the wording
   still fails the check — the exact string is usually what got legal
   sign-off, and paraphrasing regenerates legal risk.

This is deliberately dumb (no second model call to "judge" the tone) —
substring checks are fast, deterministic, and auditable. A model-based
judge is a reasonable upgrade, but it trades determinism for nuance; know
which one your compliance team would rather defend in an audit.

## The repair loop

Don't just reject a failed draft — tell the model exactly what failed and
give it one shot to fix it:

```
draft fails lint → repair_message(draft, SPECIFIC violations) → re-lint
```

Feeding back the specific violations (not just "try again") is what makes
one repair attempt usually enough. If it still fails, block — don't loop
forever chasing a message that passes; a second silent failure is a sign
the message TYPE needs a template, not more retries.

## When to reach for this pattern

- Any outbound send where "did we have permission" and "was the message
  safe" are both real, auditable questions — regulated industries
  especially (insurance, banking, healthcare, debt collection).
- You're generating text with an LLM for something that goes out under
  your brand unsupervised — the linter is the check that runs when no
  human reviews the message before it sends.

## Files
- `consent_registry.json` — per-customer channel opt-in, do-not-contact,
  consent capture date.
- `brand_safety_policy.json` — banned phrases, required disclosures per
  message type, consent freshness window.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- Substring matching for banned phrases misses paraphrases ("your payout
  is basically certain" says the same thing as "guaranteed payout" without
  tripping the check). Where's the line between "good enough, stays fast
  and auditable" and "needs a second model-based check"?
- `consent_freshness_days` is one number for every customer and channel.
  Real regulations vary by jurisdiction and channel (voice consent rules
  differ from email/SMS in most frameworks) — how much of that belongs in
  the policy JSON vs. becoming its own lookup dimension?
