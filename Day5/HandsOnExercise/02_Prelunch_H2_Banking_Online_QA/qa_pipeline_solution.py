"""
Day 5 · Pre-Lunch Lab H2 (Banking) — Online QA with Sentiment + Escalation
============================================================================
FACILITATOR REFERENCE SOLUTION.
"""

import json
import os
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

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
CONVERSATIONS_PATH = os.path.join(LAB_DIR, "conversations.json")


def load_conversations(path=CONVERSATIONS_PATH):
    with open(path) as f:
        data = json.load(f)
    return data["conversations"]


def turn_sentiment(text: str) -> int:
    words = set(text.lower().replace("!", " ").replace("?", " ").replace(",", " ").replace(".", " ").split())
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def sentiment_trend(conversation: dict) -> list:
    return [turn_sentiment(t["text"]) for t in conversation["turns"] if t["speaker"] == "customer"]


def has_sharp_negative_shift(trend: list) -> bool:
    for i in range(1, len(trend)):
        if trend[i - 1] - trend[i] >= 2:
            return True
    return False


def resolution_score(conversation: dict) -> int:
    return 1 if conversation["resolved"] else 0


def run_report(path=CONVERSATIONS_PATH):
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

    # A quick cross-check a facilitator can point out: every escalated
    # conversation should be reviewed regardless of its sentiment flag —
    # resolution, sentiment and escalation are three independent signals,
    # not a single score.
    escalated_but_not_flagged = [
        c["id"] for c in conversations
        if c.get("escalated") and c["id"] not in flagged_sentiment
    ]
    print(f"\nEscalated but NOT sentiment-flagged (still worth reviewing): {escalated_but_not_flagged}")


if __name__ == "__main__":
    run_report()
