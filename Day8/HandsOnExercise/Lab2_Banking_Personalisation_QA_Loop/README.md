# Lab-2: Banking - Ship a Smarter Offer Engine Without Shipping a Bad One

**Track:** Banking | **Industry angle:** ten customers, six product offers, and a
personalisation engine that has to prove it doesn't repeat a prior engine's mistakes

## Mental model: one registry, two jobs

```
banking_traces.json (13 historical sends, hand-crafted, some deliberately bad)
        │
        ▼
   TraceMiner.mine() ──uses──► QA check registry ◄──uses── EvalGate.run_gate()
        │                    (eligibility_respected,              │
        │                     no_banned_phrase,                   │
        │                     required_disclosure_present,        │
        │                     relevance_judge)                    │
        ▼                                                         │
  GoldenBuilder.promote()                                         │
        │                                                         │
        ▼                                                         │
   goldens.json  ─────────────────────────────────────────────────┘
   (persistent, grows                              re-runs generate_personalized_offer
    across runs)                                   against every golden, logs a
                                                     promote/reject verdict to
                                                     eval_runs.json
```

The SAME four checks judge two different things at two different times:
mining asks "did this ALREADY-SENT message violate the rules," gating asks
"does my CURRENT engine avoid violating them." One registry, one source of
truth for "what does correct look like" — not two parallel definitions that
can drift apart.

## The engine underneath: two questions, in order

```
customer
   │
   ▼
"Am I even ALLOWED to offer this?"    <- PersonalisationEngine hard-filters:
   (segment fit, credit band,             segment_fit, min_credit_band,
    balance, already held,                min_balance, not already held,
    already declined)                     not previously declined
   │
   ▼
"Which LEGAL offer is BEST?"          <- score = credit-tier bonus +
   (score the survivors)                  affordability headroom + primary-
   │                                      segment-fit bonus
   ▼
top-ranked product (or none)
```

Two of the ten seed customers (`CUST-B04`, `CUST-B09`) have ZERO eligible
products once you apply the hard filters — that's a real, correctly-handled
outcome, not an edge case to special-case away. A personalisation engine
that always finds SOMETHING to offer is a bug, not a feature.

## Why a decorator, not an if/else

```python
generate_personalized_offer(customer)      # normal use — one offer, one customer
generate_personalized_offer.run_gate()     # CI-style use — every golden, one verdict
```

`eval_gated` doesn't wrap or intercept the normal call at all — it attaches a
second capability to the same function object. That split (business-logic
call vs. gate-check call, same underlying pipeline) is what "eval-gated
updates" means in production: you don't maintain a second copy of the
pipeline to test it, you gate the one you ship.

## New SDK surface: prompt caching

`draft_offer_message`'s `system` parameter is a list of two blocks — a short
per-call instruction, and the full product catalog reference marked
`cache_control: {"type": "ephemeral"}`. That block is byte-for-byte
identical on every call this process makes (mining's re-checks don't call
it, but campaign drafting and every eval-gate re-run do) — exactly the
shape prompt caching is for: a large, static, reused prefix. At this lab's
six-product catalog the block is smaller than the ~1024-token minimum a
cache write actually needs; the point here is the mechanism, correctly
wired, at a scale you can read in one sitting. A real policy or catalog
document clears that bar without changing a line of this code.

## When to reach for this pattern

- You're generating something (an offer, a recommendation, a routed
  response) where "is this even allowed" and "is this well-matched" are
  two genuinely different questions, checked by two different mechanisms.
- You want to change HOW a pipeline decides something (new weights, a new
  prompt, a new model) and need more than "it looked fine in three manual
  tests" before it ships.
- You already have — or can reconstruct — examples of the pipeline getting
  it wrong. Those examples are worth more as regression tests than as an
  incident report nobody reads again.

## Files
- `banking_customers.json` — 10 customers, `credit_band_rank` lookup,
  segment/credit-band/balance/products-held/prior-offers per customer.
- `banking_offer_catalog.json` — 6 products, eligibility rules, pitch
  points, required disclosure, global banned phrases.
- `banking_traces.json` — 13 hand-crafted historical sends (7 clean, 6
  deterministically bad) that `TraceMiner` mines.
- `goldens.json` / `eval_runs.json` — created at runtime; gitignored, grow
  every run. Delete either to reset.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- In testing, `TraceMiner` found more than the 6 deterministically-guaranteed
  failures — `relevance_judge` occasionally flagged an otherwise-clean
  historical trace too, since mining runs the FULL registry, judge included.
  Should mining use a judge at all, or should "what already happened" stay
  strictly deterministic, with the subjective check reserved for gating a
  live candidate?
- Also observed in testing: an eval-gate run that REJECTED at pass_rate=0.875
  because ONE golden's `relevance_judge` disagreed with an otherwise fully
  correct, fully compliant offer. `pass_threshold=1.0` means one subjective
  false-negative blocks a promotion. Is 100% the right bar when one of four
  checks is a model's opinion rather than a fact? What would you set it to,
  and what do you lose either way?
- `no_repeat_declined_pitch` isn't a separate check in this lab — a declined
  product is hard-excluded inside `PersonalisationEngine.rank_offers`
  itself, so `eligibility_respected` catches it for free. What's the
  tradeoff of folding a business rule into the ranking filter vs. keeping
  it as its own named QA check with its own failure reason?
- `goldens.json` only ever grows (a customer already captured is skipped on
  re-mining). What would make a golden worth RETIRING, and who should be
  allowed to do that?
