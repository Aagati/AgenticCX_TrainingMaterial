"""
Day 5 · Pre-Lunch Lab H2 (Banking) — Online QA with Sentiment + Escalation
============================================================================

OBJECTIVE
---------
Add an online QA layer to a (simulated) live banking support stream:

  1. RESOLUTION SCORING   — reuse the idea from Lab H1: did the
     conversation resolve the customer's problem?
  2. SENTIMENT TRACKING    — score customer sentiment turn-by-turn and
     flag any conversation with a sharp NEGATIVE shift.
  3. ESCALATION ANALYSIS   — for conversations that escalated, classify
     *why*, and summarise the top escalation reasons across the batch.

You do NOT need an external API. Build a simple lexicon-based sentiment
scorer — this is exactly the kind of lightweight, explainable check a
real "Watchtower/Guardrails"-style monitor runs inline, before anything
fancier.

Fill in the TODOs, then run:
    python qa_pipeline_starter.py

WHAT "DONE" LOOKS LIKE
-----------------------
An online-QA summary report printed to the console:
  - overall resolution rate
  - the conversations flagged for a sharp negative sentiment shift
  - a breakdown of escalation reasons, ranked by frequency

STRETCH GOAL (optional)
------------------------
Right now the lexicon only looks at customer turns. Extend it to also
score AGENT turns — does agent tone ever make things worse
(e.g. a flat, unempathetic reply following an angry customer message)?
"""

import json
from collections import Counter

NEGATIVE_WORDS = {
    "worried", "worrying", "scared", "nervous", "frustrated", "frustrating",
    "ridiculous", "angry", "annoyed", "unacceptable", "terrible", "awful",
    "again", "inconvenient", "urgent", "urgently",
}
POSITIVE_WORDS = {
    "thanks", "thank", "great", "perfect", "awesome", "appreciate",
    "relief", "helpful", "happy",
}


def load_conversations(path="conversations.json"):
    with open(path) as f:
        data = json.load(f)
    return data["conversations"]


def turn_sentiment(text: str) -> int:
    """
    TODO 1 — Score a single turn's text as +1 (positive), -1 (negative),
    or 0 (neutral), using NEGATIVE_WORDS / POSITIVE_WORDS above.

    Keep it simple: lowercase the text, count matches against each
    word list, and return the sign of (positive_count - negative_count).
    """
    # YOUR CODE HERE
    raise NotImplementedError


def sentiment_trend(conversation: dict) -> list:
    """
    TODO 2 — Return a list of per-turn sentiment scores for every
    CUSTOMER turn in the conversation, in order, using turn_sentiment().
    """
    # YOUR CODE HERE
    raise NotImplementedError


def has_sharp_negative_shift(trend: list) -> bool:
    """
    TODO 3 — Given a sentiment trend (list of -1/0/1), return True if
    sentiment drops sharply at any point — e.g. from neutral/positive
    to negative between two consecutive customer turns.

    Define "sharp" as a drop of 2 or more between consecutive turns
    (e.g. +1 -> -1).
    """
    # YOUR CODE HERE
    raise NotImplementedError


def resolution_score(conversation: dict) -> int:
    """
    TODO 4 — Same idea as Lab H1: return 1 if resolved, 0 if not,
    using conversation["resolved"].
    """
    # YOUR CODE HERE
    raise NotImplementedError


def run_report(path="conversations.json"):
    conversations = load_conversations(path)

    flagged_sentiment = []
    escalation_reasons = Counter()
    resolved_count = 0

    for c in conversations:
        resolved_count += resolution_score(c)

        trend = sentiment_trend(c)
        if has_sharp_negative_shift(trend):
            flagged_sentiment.append(c["id"])

        if c.get("escalated"):
            escalation_reasons[c["escalation_reason"]] += 1

    print("=== Online QA Summary ===")
    print(f"Conversations scored: {len(conversations)}")
    print(f"Resolution rate: {resolved_count/len(conversations):.0%}")
    print(f"\nFlagged for sharp negative sentiment shift: {flagged_sentiment}")
    print("\nEscalation reasons (most common first):")
    for reason, count in escalation_reasons.most_common():
        print(f"  - {reason}: {count}")


if __name__ == "__main__":
    run_report()
