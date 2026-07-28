"""
AM · H2 — Insurance Supervisor Routing (STARTER)

Design note: the point of this lab is that you CANNOT get the same result by
writing one bigger prompt. Merging "be empathetic about claim status" with
"cite clause ids and never guess" produces an agent that is vaguely both and
reliably neither. Splitting them gives each specialist one persona and one
slice of data — and gives you a routing decision you can log, measure, and
fix when it drifts.

Watch the scoping as you build: the claims specialist should never receive
the policy clauses, and vice versa. Keeping the data apart is what stops a
specialist from improvising outside its lane. An instruction it might ignore
is a much weaker guarantee than context it simply doesn't have.

Run it from this directory: `python starter.py`
"""

import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("mock_data.json") as f:
    DATA = json.load(f)


def _text(response) -> str:
    """Provided — use this instead of response.content[0].text in all three
    TODOs below.

    content[0] is often a ThinkingBlock (the model reasoning before it
    answers), and ThinkingBlock has no .text attribute. The shortcut dies with
    a confusing AttributeError — and only on some turns, so it passes while
    you're testing and fails later. Always search by block type.
    """
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def classify_intent(message: str) -> str:
    """
    TODO 1: Use a narrow Claude call to classify `message` as exactly
    "claims" or "policy". Reply format should be enforced via the system
    prompt (reply with ONLY one word). Return the lowercase word.

    Set max_tokens low (~10). It makes the call fast and cheap, and it stops
    the model from drifting into an explanation you'd then have to parse.
    Remember .strip().lower() — trailing whitespace and a capital C are the
    two things that will silently break your == comparison later.
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

    Render each clause with its id visible, e.g. "[POL-010] Roadside
    Assistance\\n<text>". If you ask for citations but don't put the ids in
    the context, the model will invent ones that look right.
    """
    raise NotImplementedError


def route_and_respond(message: str):
    """
    TODO 4: Classify the message, call the matching specialist, and return
    a tuple (specialist_name, reply_text).

    Return the specialist NAME, not just the reply — that's the audit trail.
    Routing quality is the first thing to degrade in a system like this, and
    you can't measure a decision you never recorded.

    Also decide what happens when the classifier returns something that is
    neither word. Falling through to policy is defensible; falling over is
    not.
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
