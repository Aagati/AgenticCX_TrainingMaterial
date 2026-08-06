# Lab-2: Insurance - One Guardrail Isn't a Guardrail Stack

**Track:** Insurance | **Industry angle:** sixteen requests, four roles, three
jurisdictions, and one append-only file that has to still be believable in a year

## Mental model: nine layers, three verdicts, one chain

```
raw request (actor_id, customer_id, action, payout_amount, message)
   │
   ├──► resolve identity: actor -> role -> capabilities        (rbac_roles.json)
   └──► resolve subject:  customer -> jurisdiction -> rules     (policy_holders.json
   │                                                             + jurisdiction_rules.json)
   ▼
┌── GuardrailStack.evaluate() — ordered, short-circuits on BLOCK ──────────────┐
│  10  injection_probe                INPUT       PASS | BLOCK                │
│  20  authority_claim_probe          INPUT       PASS | BLOCK                │
│  30  rbac_action_allowed            PERMISSION  PASS | BLOCK                │
│  40  rbac_scope_and_authority       PERMISSION  PASS | BLOCK                │
│  ──────────────  draft_claim_response()  happens HERE  ──────────────────   │
│  50  generation_terminated_cleanly  OUTPUT      PASS | BLOCK   <- stop_reason│
│  60  jurisdiction_disclosure_present COMPLIANCE PASS | REDACT (append)      │
│  70  role_scoped_field_leak         OUTPUT      PASS | REDACT (mask)        │
│  80  prohibited_claim               COMPLIANCE  PASS | BLOCK  (per-state!)  │
│  90  audit_chain_write              AUDIT       always runs, never decides  │
└───────────────────────────────────────────────────────────────────────────┘
   │
   ▼
guardrail_audit_log.json
   AUD-00001 ──hash──► AUD-00002 ──hash──► AUD-00003 ──hash──► AUD-00004
   edit AUD-00002 and every hash from AUD-00002 forward stops matching
```

The SAME nine layers judge every request, whether it's a live customer
message or an internal agent action - one registry, one source of truth for
"what does correct look like," not two parallel definitions that can drift
apart.

## PASS, BLOCK, REDACT - and why the third one is the whole idea

| Verdict | What happens | Example in this lab |
|---|---|---|
| PASS | Payload unchanged, walk continues | A clean request with nothing to fix |
| BLOCK | Walk stops here, nothing ships | `injection_probe` catching "ignore all previous instructions" |
| **REDACT** | Payload **replaced**, walk continues | `jurisdiction_disclosure_present` appending a missing sentence |

A layer that can only say yes or no is a filter. A layer that can hand the
next layer a DIFFERENT payload is a stack. Layer 60 appends a sentence;
layer 70 masks a number in the sentence layer 60 just appended; layer 80
judges the result. Reorder those three and you get a different answer -
which is why `order` is an explicit integer, not list position.

## Why a stack, not a bigger `if`

| | Day 4's single guardrail | Day 9's stack |
|---|---|---|
| Shape | `if input_guardrail(msg)["flagged"]: return refusal` | ordered registry of layers, each returning a verdict |
| Adding a check | edit the function | one `@register_guardrail(...)` - no other file changes |
| Verdicts | flagged / not flagged | PASS continues · BLOCK terminates · **REDACT transforms and continues** |
| Identity | one user, one resource (`owns_orders`) | role → capability set, payout ceiling, own-book scope |
| Compliance | one policy for everyone | jurisdiction-keyed table, looked up per customer |
| Audit | append-only Python list, in memory, dies with the process | hash-chained, on disk, tamper-**evident**, survives restarts |
| Catches | a bad input | a bad input, a bad **actor**, a bad **jurisdiction**, and a bad **output** |
| Failure directions counted | missed blocks | missed blocks **and** false blocks |

## Three pairs that prove the point (verified in testing — real API run)

- **REQ-009 / REQ-010** — same claim amount ($3,400), two jurisdictions.
  CA's `requires_written_confirmation_above` is 2,500, so REQ-009 gets a
  disclosure appended (`jurisdiction_disclosure_present` redacts). TX's is
  10,000, so the identical amount doesn't trigger it — REQ-010 already
  carries TX's disclosure verbatim, so nothing gets added at all.
- **REQ-011 / REQ-012** — same policy number appears in both drafts.
  `AG-101` is `tier1_support` (`can_view_full_policy_number: false`), so
  REQ-011's number gets masked to `POL-IN-****1001`. `AG-450` is
  `fraud_investigator` (full visibility), so REQ-012's identical number
  passes through unmasked.
- **REQ-013 / REQ-014** — the exact phrase "this is our final decision on
  your claim" appears in both drafts. NY prohibits it (REQ-013 blocks at
  `prohibited_claim`); TX doesn't (REQ-014 passes). Same string, two
  verdicts, because `prohibited_claim` reads `context["jurisdiction"]`'s own
  list, never a global one.
- **Bonus pair, REQ-005 / REQ-008** — the identical $8,000 payout request.
  `claims_adjuster`'s ceiling is $5,000 (blocks at `rbac_scope_and_authority`);
  `senior_adjuster`'s is $50,000 (passes). Same money, two roles, two
  verdicts.

Run the corpus and every fact above is exact, every run: **7 of 16 requests
BLOCK** (`REQ-002/003/004/005/006/007/013`), **zero missed blocks, zero false
blocks, zero wrong-layer verdicts** - no live call decides any block in this
corpus, so nothing here depends on a model's mood.

## Tamper-evident, not tamper-proof

`HashChainedAuditLog.verify()` catches a single edited entry at its exact
index - and then, if you also recompute that entry's OWN hash to make it
"consistent," verify() catches it again one entry LATER, because the next
entry's `prev_hash` still points at the original. That's what "chained"
buys over "hashed": editing entry 2 doesn't just break entry 2, it breaks
everything after it, and re-forging one entry just moves the break forward.
What it does NOT buy: anyone with write access to `guardrail_audit_log.json`
can re-forge the ENTIRE chain from the tampered entry onward, given enough
patience - a hash chain proves tampering happened, it doesn't prevent it.
Closing that gap needs something outside this process: external anchoring
(publish the latest hash somewhere the app can't rewrite), a signing key the
app itself never holds, or WORM (write-once) storage for the file.

## New SDK surface: `stop_reason` is a guardrail layer you didn't write

- `response.stop_reason` values that matter to a compliance pipeline:
  `"end_turn"` (normal), `"refusal"` (the model's own safety classifiers
  declined), `"max_tokens"` (truncated - and the disclosure is the last
  sentence).
- **`claude-sonnet-5` reasons by default.** Left alone, a chunk of every
  `max_tokens` budget goes to an invisible thinking pass before a single
  word of the actual reply is written - at `max_tokens=300` in early
  testing, that was enough to trip `generation_terminated_cleanly` on
  perfectly ordinary requests. `draft_claim_response` passes
  `thinking={"type": "disabled"}` because a short, policy-constrained claims
  reply doesn't need extended reasoning, and a student who forgets this
  will watch layer 50 block requests that have nothing wrong with them.
- Layers 1-4 and 6-8 are yours. Layer 5 is Anthropic's. You didn't write it,
  you can't tune it, and your audit trail still has to record that it fired
  - because in a regulated context "the model refused" is a materially
  different event from "the agent answered."
- Explicitly **not new**: prompt caching on the rulebook block (Day 8
  Lab-2's mechanic) and the `@register_check`-shaped registry (Day 8 Lab-2
  and Capstone). Naming what's reused is how this stays honest about what
  Day 9 actually adds.

## When to reach for this pattern

- More than one team owns "is this allowed" - security owns injection
  defense, compliance owns disclosures, legal owns banned phrases, and none
  of them wants to review the others' code to add a check.
- The answer depends on who is asking as much as on what was asked - the
  same policy number, the same payout amount, is fine for one role and not
  another.
- You'd have to explain a blocked (or allowed) decision to someone six
  months later, and "the code did something" isn't an acceptable answer.

## Files
- `rbac_roles.json` - 4 roles (`tier1_support`, `claims_adjuster`,
  `senior_adjuster`, `fraud_investigator`) and 4 actors with their
  assigned-customer books.
- `jurisdiction_rules.json` - NY/CA/TX plus DEFAULT, each with its own
  disclosure, written-confirmation threshold, and prohibited phrases.
- `policy_holders.json` - 10 customers; `CUST-IN08`'s jurisdiction ("MA")
  isn't in the table, exercising the DEFAULT fallback.
- `adversarial_requests.json` - 16 requests, 7 adversarial.
- `guardrail_audit_log.json` - created at runtime; gitignored, grows every
  run. Delete it to reset the chain to genesis.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- Layer 90 runs even when layer 10 blocked. What's the argument for
  skipping it on a blocked request - cost, noise, storing attacker-supplied
  text - and why does each argument lose?
- `REQ-009`/`REQ-010`'s table lives in a JSON file anyone with repo access
  can edit. Should jurisdiction thresholds live in code, in a file like
  this, or in a system your legal team can change without a deploy - and
  who signs off on a change to it?
- Layer 70 **redacts** rather than blocks. When is masking the correct
  answer, and when is it just shipping the violation with extra steps?
- `run_corpus` counts false blocks as failures alongside missed blocks. If
  you could only optimize one direction, which would you pick for a claims
  assistant - and would your answer change for a payments assistant?
- `guard_field_leak` only knows about ONE pattern (`POL-IN-####`). What's
  the cost of a stack whose output layers are pattern-specific versus one
  that tries to generalize to "any sensitive-looking field" - and which
  would you ship first?
