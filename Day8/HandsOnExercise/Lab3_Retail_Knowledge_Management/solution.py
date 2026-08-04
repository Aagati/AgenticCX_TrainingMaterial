"""
Lab-3: Retail - Half the Knowledge Base Is Out of Date and Nobody Noticed.

kb_articles.json is 16 articles. Two pairs of them cover the SAME topic —
one current, one superseded (ART-007/ART-008 on loyalty points,
ART-014/ART-015 on holiday shipping deadlines) — and in both pairs, plain
keyword relevance ranks the OLD one first, because it happens to share more
literal words with a natural question about the topic. Relevance and
correctness are different questions. This lab is small on purpose — most of
this day's mechanics were covered in Lab-1/Lab-2; this is the one new,
contained idea: a retrieval system has to manage its own knowledge, not just
rank it.

KnowledgeBase.retrieve() answers "what matches" (deterministic keyword/tag
scoring). flag_staleness() answers "can I trust it" (explicit
status=deprecated, or last_updated older than a year). retrieve_for_customer()
composes both, PLUS a thin personalisation boost, and — the one guarantee
this lab makes — never lets a deprecated article sit in the #1 slot when a
named replacement exists; it swaps the replacement in instead. That's the
whole lab: rank, judge trust, fix the top slot, then ground a real answer in
whatever survives.

This lab is intentionally self-paced and safe to skip — nothing in the
capstone requires you to have finished it. The capstone ships its own
KnowledgeBase, already built, with the same mechanics explained inline.
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
        """Deterministic. Pure relevance, no notion of trust yet — a
        deprecated article scores exactly as well as its replacement if
        they share the same words, which is precisely the trap the rest
        of this file exists to catch."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored = []
        for article in ARTICLES:
            tag_hits = sum(1 for tag in article["tags"] if tag.lower() in query_lower)
            title_words = set(
                article["title"].lower().replace("-", " ").replace("(", "").replace(")", "").split()
            )
            title_overlap = len(query_words & title_words)
            score = 2 * tag_hits + title_overlap
            if score > 0:
                scored.append({**article, "score": score})
        scored.sort(key=lambda a: a["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def retrieve_for_customer(query: str, customer: dict, top_k: int = 3) -> list[dict]:
        """Composes retrieve() + a personalisation boost + staleness
        judgment + one safety guarantee: the #1 result is never a
        deprecated article when a named replacement exists."""
        results = KnowledgeBase.retrieve(query, top_k=top_k)
        for article in results:
            if customer["segment"] in article["segment_relevance"]:
                article["score"] += 0.5
        results.sort(key=lambda a: a["score"], reverse=True)
        results = flag_staleness(results, NOW)

        if results and results[0]["staleness_flag"] == "deprecated" and results[0]["superseded_by"]:
            replacement_id = results[0]["superseded_by"]
            replacement = ARTICLES_BY_ID[replacement_id]
            replacement_entry = flag_staleness(
                [{**replacement, "score": results[0]["score"], "auto_substituted_for": results[0]["article_id"]}], NOW
            )[0]
            # drop any separate occurrence of the replacement further down before promoting it,
            # so it doesn't end up listed twice
            rest = [r for r in results[1:] if r["article_id"] != replacement_id]
            results = [replacement_entry] + rest
            results = results[:top_k]

        return results


def flag_staleness(articles: list[dict], now: date = NOW) -> list[dict]:
    """Given — two independent staleness signals: an explicit status flag
    (hard) and last_updated age (soft). An article can be old but still
    active (nobody's gotten around to reviewing it) or explicitly retired
    with a pointer to what replaced it."""
    flagged = []
    for article in articles:
        if article["status"] == "deprecated":
            flag = "deprecated"
        elif (now - date.fromisoformat(article["last_updated"])).days > STALENESS_WINDOW_DAYS:
            flag = "stale"
        else:
            flag = None
        flagged.append({**article, "staleness_flag": flag})
    return flagged


def draft_grounded_response(query: str, customer: dict, articles: list[dict]) -> str:
    """Real sonnet call. Grounds strictly in the provided articles — a
    defensive instruction against ever citing a [LEGACY]/[OUTDATED]-marked
    body is a backstop, not the primary defense; the primary defense is
    that retrieve_for_customer already kept a deprecated article out of
    the #1 slot whenever it could."""
    if not articles:
        return "I don't have a knowledge base article that answers this one — routing to a human agent."
    context = "\n\n".join(
        f"[{a['article_id']}] {a['title']}"
        + (" (NOTE: not reviewed in over a year — mention it may be outdated)" if a["staleness_flag"] == "stale" else "")
        + f"\n{a['body']}"
        for a in articles
    )
    system = (
        "You are a retail support assistant. Answer the customer's question using ONLY the KB articles "
        "provided below — never invent a policy detail that isn't in them. Cite the article you used by "
        "its title. If an article is marked as not reviewed in over a year, briefly note the customer may "
        "want to confirm current terms. Never rely on an article whose body is marked [LEGACY] or "
        "[OUTDATED] — if that's the only thing provided, say you're not fully certain and offer to "
        "connect them with a human instead of stating its contents as current fact."
    )
    user = f"Customer segment: {customer['segment']}\nQuestion: {query}\n\nAvailable articles:\n{context}"
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=400, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


def log_kb_query(customer: dict, query: str, results: list[dict], response: str, log_path: Path = KB_USAGE_LOG_FILE) -> dict:
    """Given — persistent, dedicated JSON file. Every query this KB ever
    answers (and what it cited, and whether that citation was flagged)
    accumulates here across runs, not just in memory for this process."""
    history = json.load(open(log_path, encoding="utf-8")) if log_path.exists() else []
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_id": customer["customer_id"],
        "query": query,
        "top_article_id": results[0]["article_id"] if results else None,
        "staleness_flags_present": [r["staleness_flag"] for r in results if r["staleness_flag"]],
        "response": response,
    }
    history.append(record)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return record


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
