# Lab-3: Retail - Half the Knowledge Base Is Out of Date and Nobody Noticed

**Track:** Retail | **Industry angle:** a 16-article support KB where two topics
have both a current article and a superseded one sitting side by side

**Facilitator note — this lab is self-paced and safe to skip.** Most of this
day's mechanics (scoring, filtering, grounded drafting, persistent logs) were
already covered in Lab-1/Lab-2. This lab is deliberately small — one new,
contained idea. The capstone does not depend on it: it ships its own
`KnowledgeBase`, already built, with every mechanic below explained inline.

## Mental model: relevance and trust are different questions

```
"how do loyalty points work"
        │
        ▼
KnowledgeBase.retrieve()          <- pure keyword/tag relevance
        │
        ├─ ART-007 "Legacy Loyalty Points Program"   score 6   [DEPRECATED]
        ├─ ART-008 "Rewards+ Loyalty Program (2026)"  score 5   [current]
        └─ ART-002 "Loyalty-Gold Extended Return..."  score 3
        │
        ▼
   + personalisation boost, + flag_staleness()
        │
        ▼
retrieve_for_customer()'s ONE guarantee:
  is results[0] deprecated AND has a replacement? -> swap it in.
        │
        ▼
   ART-008 promoted to #1, ART-007 dropped        <- trust corrected the rank
```

The deprecated article doesn't lose on relevance — it often WINS. "Legacy
Loyalty Points Program" literally contains the word "points"; the current
article's title doesn't. A retrieval system that only ranks by relevance
will confidently hand a customer outdated policy, worded convincingly,
citing a real article. That's the failure mode this lab targets.

## Two independent staleness signals

| Signal | What it catches | Example in this KB |
|---|---|---|
| `status == "deprecated"` | Someone explicitly retired this article and named what replaced it | ART-007 → ART-008, ART-014 → ART-015 |
| `last_updated` older than 365 days | Nobody's reviewed it recently — not necessarily WRONG, just unverified | ART-012 (Gift Card Terms, last touched 2025-03-01) |

The first is a hard fact from the CMS. The second is a proxy — old doesn't
always mean wrong, but it's the only signal available for content nobody
explicitly flagged. `draft_grounded_response` treats them differently: a
deprecated article gets swapped out before the model ever sees it as the
top pick; a merely-stale one gets cited WITH a caveat.

## Why the guarantee only covers the #1 slot

Building `retrieve_for_customer` surfaced a real edge case worth knowing
about rather than engineering around: for the query "how much is shipping
for a small order," `ART-014` (2025, deprecated) ties `ART-003`/`ART-004` at
score 3 — but loses the tie on list order and lands 3rd, not 1st. It survives
in the results, correctly flagged `"deprecated"`, uncorrected. A production
system would eventually want every slot clean, not just the top one — this
lab stops at "the #1 citation is never wrong" because that's the one a
grounded response actually leans on, and chasing every slot is real scope
beyond what a lightweight lab needs to prove the mechanism.

## When to reach for this pattern

- Your KB has ever had a policy, price, or program change — which is to
  say, any KB more than a few months old.
- Retrieval is scored by relevance (keyword, embedding, whatever) with no
  separate notion of "is this still true."
- Nobody owns "review articles that haven't been touched in N days" as an
  actual process — `flag_staleness`'s age-based check is what that process
  would query against.

## Files
- `kb_articles.json` — 16 articles across 7 categories; 2 deprecated/
  replacement pairs, 1 aged-but-active article.
- `retail_customers.json` — 6 customers, one representative query each.
- `kb_usage_log.json` — created at runtime; gitignored, grows every run.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- This KB's "deprecated" status and `superseded_by` pointer are hand-set in
  the JSON. In a real CMS, who sets that pointer — the author of the OLD
  article (who may not know what replaced it yet) or the author of the
  NEW one (who does)?
- The tie-break that lets ART-014 slip to 3rd instead of 1st for CUST-R05
  was luck of list order, not design. What's a more principled tie-break
  rule, and would it have been worth the extra complexity for this lab?
- `flag_staleness`'s 365-day window is one number for every article,
  regardless of category. Does a shipping-deadline article and a return
  policy article deserve the same staleness window?
