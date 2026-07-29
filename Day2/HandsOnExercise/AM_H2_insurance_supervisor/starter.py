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

Run: `python starter.py` — paths resolve relative to this file, so any
working directory is fine.
"""

import json
import os
import sys
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

# Windows consoles default to cp1252 and crash when the model emits an arrow,
# em-dash or curly quote. Force UTF-8 so a print() cannot kill the lab.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = Anthropic()
MODEL = "claude-sonnet-5"

# Resolve data next to THIS file, so the lab runs from any working directory.
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(DATA_DIR, "mock_data.json")) as f:
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

    We can also use a very cheap/lightweight model for this classification task,
    since we don't need token expensive reasoning nor we need to generate long responses.
    It's a simple 1 word in - 1 word out classification so a small model/cheap/open source model can
    also be used, for example = "claude-haiku-4-5-20251001" (claude Haiku 4.5)
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=10,
        system=(
            "Classify the following customer message as either 'claims' or 'policy'."
            "'claims' (filing or checking the status of an insurance claim) or 'policy' (questions about coverage, clauses, or terms of the insurance policy)."
            "(coverage/policy wording questions). Reply with ONLY one word: 'claims' or 'policy'."
        ),
        messages=[{"role": "user", "content": message}]
    )
    return _text(response).strip().lower()

# model = 'claims', return = 'claims'
# model = 'polic y', return = 'policy'
# model = 'CLAIM S', return = 'claims'


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
    claims_context = json.dumps(DATA["claims"], indent=2)
    system = f"""
        You are a Claims Specialist. You have access to the following claims data:
        You are empathetic and focused on providing claims statuses and next steps
        Here is the claims data you have access to: {claims_context}

        If asked a general policy coverage question, say that it is outside what you can handle.
        and tell the user that you will REDIRECT them to the Policy team."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": message}]
    )

    return _text(response)



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
    clauses_context = "\n\n".join(f"[{c['id']}] {c['title']}\n{c['text']}" for c in DATA["policy_clauses"])
    system = f"""
            You are a Policy Specialist. You have access to the following policy clauses data:
            {clauses_context}
            You are precise and citation-oriented, Answer ONLY using the policy clauses attached above.
            citing the clause ID (ex. POL-001) for every factual claim, if the answer isnt in these clauses
            SAY explicitly that you don't have such information rather than guessing or using your own internal knowledge.
            If asked about claim statuses, SPECIFY it is outside of your scope and 
            redirect the user to the Claims team."""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": message}]
    )

    return _text(response)


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

    intent = classify_intent(message)
    if intent == "claims":
        reply = claims_specialist_reply(message)
        return "Claims Specialist: ", reply
    elif intent == "policy":
        reply = policy_specialist_reply(message)
        return "Policy Specialist: ", reply


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
