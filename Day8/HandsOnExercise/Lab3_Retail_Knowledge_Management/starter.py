"""
Lab-3: Retail - Half the Knowledge Base Is Out of Date and Nobody Noticed (STARTER).

kb_articles.json is 16 articles. Two pairs of them cover the SAME topic —
one current, one superseded (ART-007/ART-008 on loyalty points,
ART-014/ART-015 on holiday shipping deadlines) — and in both pairs, plain
keyword relevance ranks the OLD one first, because it happens to share more
literal words with a natural question about the topic. Relevance and
correctness are different questions. This lab is small on purpose — most of
this day's mechanics were covered in Lab-1/Lab-2; this is the one new,
contained idea: a retrieval system has to manage its own knowledge, not just
rank it.

You'll build:
  1. KnowledgeBase.retrieve — deterministic keyword/tag relevance scoring.
  2. flag_staleness — two independent trust signals (explicit deprecation,
     age-based staleness).
  3. KnowledgeBase.retrieve_for_customer — composes both, adds a thin
     personalisation boost, and guarantees the #1 slot is never a
     deprecated article when a named replacement exists.
  4. draft_grounded_response — the real drafting call, grounded strictly
     in whatever retrieve_for_customer returned.
  5. log_kb_query — persists every query to kb_usage_log.json.

This lab is self-paced and safe to skip — nothing in the capstone requires
you to have finished it. The capstone ships its own KnowledgeBase, already
built, with the same mechanics explained inline.
"""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "kb_articles.json", encoding="utf-8") as f:
    ARTICLES = json.load(f)["articles"]
with open(DATA_DIR / "retail_customers.json", encoding="utf-8") as f:
    CUSTOMERS = json.load(f)["customers"]

ARTICLES_BY_ID = {a["article_id"]: a for a in ARTICLES}
KB_USAGE_LOG_FILE = DATA_DIR / "kb_usage_log.json"

STALENESS_WINDOW_DAYS = 365
NOW = date(2026, 8, 4)  # fixed reference date, kept naive on purpose — same convention as Day7 H3's NOW

client = Anthropic()


class KnowledgeBase:
    @staticmethod
    def retrieve(query: str, top_k: int = 3) -> list[dict]:
        """
        TODO 1: Deterministic relevance scoring, no notion of trust yet.
        For each article in ARTICLES: tag_hits = count of article["tags"]
        whose text appears as a substring of query.lower() (tags can be
        multi-word, e.g. "gift card" — substring-of-the-raw-query-string
        is what makes that work). title_overlap = size of the set
        intersection between query.lower().split() and the article's
        title words (lowercased, with "-", "(", ")" replaced/stripped
        before splitting, so "Loyalty-Gold" contributes both "loyalty"
        and "gold" as separate words). score = 2*tag_hits + title_overlap.
        Keep only articles with score > 0 (don't pad results with
        irrelevant matches), sort highest-first, return the top_k.
        """
        raise NotImplementedError

    @staticmethod
    def retrieve_for_customer(query: str, customer: dict, top_k: int = 3) -> list[dict]:
        """
        TODO 3: Call KnowledgeBase.retrieve(query, top_k), then add +0.5
        to any result whose segment_relevance includes customer["segment"],
        re-sort by score, then run flag_staleness(results, NOW).
        THE GUARANTEE: if the #1 result's staleness_flag == "deprecated"
        and it has a superseded_by, replace it with that replacement
        article instead (score-carried-over is fine, staleness-flag it
        fresh via flag_staleness too — the replacement should usually
        come back with staleness_flag None). Watch for the replacement
        ALREADY being present further down your results (both deprecated
        pairs in this fixture have their replacement naturally scoring
        well too) — drop that separate occurrence before promoting the
        fresh copy to #1, so it isn't listed twice. This guarantee only
        covers the #1 slot; a deprecated article surviving further down
        the list as secondary context is acceptable for this lab.
        """
        raise NotImplementedError


def flag_staleness(articles: list[dict], now: date = NOW) -> list[dict]:
    """
    TODO 2: Two independent trust signals, checked per article: if
    article["status"] == "deprecated", staleness_flag = "deprecated".
    Else if (now - article["last_updated"] as a date).days exceeds
    STALENESS_WINDOW_DAYS, staleness_flag = "stale". Else None. Return
    every article with this key added (don't mutate the ones from
    ARTICLES in place — build new dicts).
    """
    raise NotImplementedError


def draft_grounded_response(query: str, customer: dict, articles: list[dict]) -> str:
    """
    TODO 4: If `articles` is empty, return a short "I don't have an
    article for this — routing to a human" sentence, no model call. Else
    real sonnet call: system prompt says answer using ONLY the provided
    articles (never invent a policy detail), cite the article used by
    title, add a brief "may want to confirm current terms" note for any
    article whose staleness_flag == "stale", and NEVER state the contents
    of a [LEGACY]/[OUTDATED]-marked body as current fact (a defensive
    backstop — retrieve_for_customer should have already kept a
    deprecated article out of the #1 slot). user content: customer
    segment + the question + each article's id/title/body (include the
    staleness note inline for "stale" ones so the model sees it).
    client.messages.create(model=MODEL_DRAFT, max_tokens=400, system=...,
    messages=[{"role": "user", "content": ...}]) — return the text,
    stripped.
    """
    raise NotImplementedError


def log_kb_query(customer: dict, query: str, results: list[dict], response: str, log_path: Path = KB_USAGE_LOG_FILE) -> dict:
    """
    TODO 5: Load log_path if it exists (a JSON list), else start empty.
    Append one record: {"timestamp": <UTC ISO>, "customer_id":...,
    "query":..., "top_article_id": results[0]'s id or None if empty,
    "staleness_flags_present": [every non-None staleness_flag across
    results], "response":...}. Write the whole list back (indent=2).
    Return the record.
    """
    raise NotImplementedError


if __name__ == "__main__":
    print(f"=== Lab-3: Retail Knowledge Management — {len(ARTICLES)} articles, {len(CUSTOMERS)} queries ===\n")

    for customer in CUSTOMERS:
        query = customer["query"]
        print(f"--- {customer['customer_id']} ({customer['segment']}): \"{query}\" ---")

        raw = KnowledgeBase.retrieve(query, top_k=3)
        print(f"  Raw relevance ranking: {[(a['article_id'], a['score']) for a in raw]}")

        results = KnowledgeBase.retrieve_for_customer(query, customer, top_k=3)
        top = results[0] if results else None
        if top and top.get("auto_substituted_for"):
            print(f"  -> top pick {top['article_id']} AUTO-SUBSTITUTED for deprecated {top['auto_substituted_for']}")
        print(f"  Final ranking: {[(a['article_id'], a['staleness_flag']) for a in results]}")

        response = draft_grounded_response(query, customer, results)
        print(f"  Response: \"{response}\"")

        record = log_kb_query(customer, query, results, response)
        print()

    print(f"--- Logged {len(CUSTOMERS)} queries -> {KB_USAGE_LOG_FILE.name} ---")

# Expected (hand-verified against kb_articles.json):
# CUST-R01 "...return...gold member": ART-002 wins outright (score 6 -> 6.5
# boosted) over ART-001 (score 3) — no substitution needed.
# CUST-R04 "how do loyalty points work": raw ranking puts DEPRECATED ART-007
# on top (score 6 -> 6.5 boosted, beats ART-008's 5 -> 5.5) purely on keyword
# overlap ("points" is in ART-007's title, not ART-008's) — retrieve_for_customer
# must auto-substitute ART-008 into the #1 slot.
# CUST-R06 "...holiday shipping deadlines...": raw ranking TIES ART-014
# (deprecated) and ART-015 at 9-9, with ART-014 winning the tie purely by
# appearing first in kb_articles.json — again requires substitution.
# CUST-R02/03 have no deprecated article in contention — plain top-1 is correct,
# no substitution fires. CUST-R05 is the scope-boundary case: ART-014
# (deprecated) ties ART-003/ART-004 at score 3 on shared "shipping" — but loses
# the tie (list order puts it 3rd, not 1st), so it correctly survives in the
# results UNFLAGGED for substitution (only the #1 slot carries the guarantee).
# Drafting responses are real model calls; don't hardcode exact wording, but
# every response should cite a NON-deprecated article by title and none should
# surface "[LEGACY]" or "[OUTDATED]" text.
