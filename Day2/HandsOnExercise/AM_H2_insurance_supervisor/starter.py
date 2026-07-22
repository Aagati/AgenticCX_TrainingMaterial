"""
AM · H2 — Insurance Supervisor Routing (STARTER)
"""

import json
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("mock_data.json") as f:
    DATA = json.load(f)


def classify_intent(message: str) -> str:
    """
    TODO 1: Use a narrow Claude call to classify `message` as exactly
    "claims" or "policy". Reply format should be enforced via the system
    prompt (reply with ONLY one word). Return the lowercase word.
    """
    raise NotImplementedError


def claims_specialist_reply(message: str) -> str:
    """
    TODO 2: Build a system prompt for a Claims Specialist persona:
      - empathetic, status/next-step focused
      - has access to DATA["claims"] as its scoped knowledge (include the
        relevant claims in the context — for this lab, it's fine to include
        all of them, there are only 2)
      - should NOT answer general policy coverage questions; if asked one,
        it should say that's outside what it handles
    Call Claude with this system prompt and the customer message, return
    the reply text.
    """
    raise NotImplementedError


def policy_specialist_reply(message: str) -> str:
    """
    TODO 3: Build a system prompt for a Policy Specialist persona:
      - precise, citation-oriented (cite POL- ids), grounded ONLY in
        DATA["policy_clauses"]
      - should NOT discuss claim status; if asked, say that's outside what
        it handles
      - if the answer isn't in the provided clauses, say so rather than
        guessing (same grounding pattern as Day 1)
    Call Claude with this system prompt and the customer message, return
    the reply text.
    """
    raise NotImplementedError


def route_and_respond(message: str):
    """
    TODO 4: Classify the message, call the matching specialist, and return
    a tuple (specialist_name, reply_text).
    """
    raise NotImplementedError


if __name__ == "__main__":
    test_messages = [
        "What's the status of my auto claim, CLM-3391?",
        "Does my auto policy cover a tow if my car breaks down?",
        "My basement flooded from a burst pipe, am I covered?",
    ]
    for m in test_messages:
        specialist, reply = route_and_respond(m)
        print(f"\nCUSTOMER: {m}")
        print(f"[routed to: {specialist}]")
        print(f"AGENT: {reply}")
