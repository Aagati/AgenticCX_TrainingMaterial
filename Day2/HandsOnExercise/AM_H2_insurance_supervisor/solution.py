"""
AM · H2 — Insurance Supervisor Routing (REFERENCE SOLUTION)

THE PATTERN: one classifier in front of several narrow specialists.

Why not a single agent with all the data and all the instructions? Because
prompts don't compose. Merge "be empathetic about claims" with "cite clause
ids and never guess" into one system prompt and you get an agent that is
vaguely both and reliably neither — it invents clause ids to sound precise,
or gets chatty where it should cite. Each specialist here has ONE persona and
ONE slice of data, so each can be evaluated, tuned, and owned separately.

Three parts, in run order:
    1. classify_intent  -> a cheap, narrow call that returns one word
    2. specialists      -> two personas, two disjoint knowledge scopes
    3. route_and_respond-> plain Python if/else on the classifier's answer

Compare with solution_langgraph.py, which is the same three parts expressed
as an explicit graph.
"""

import json
import os
import sys
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

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
    """Pull the reply text out of a response.

    Do NOT write response.content[0].text. content[0] is often a
    ThinkingBlock — the model reasoning before it answers — and ThinkingBlock
    has no .text attribute, so that shortcut dies with a confusing
    AttributeError. Worse, it only happens on some turns, so it passes in
    testing and fails in front of a customer. Always search by block type.
    """
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


# ---------- 1. The classifier ----------

def classify_intent(message: str) -> str:
    """One word in, one word out.

    max_tokens=10 is doing real work: it makes the call fast and cheap, and it
    physically prevents the model from wandering into an explanation. Routing
    happens on every single message, so this is the call whose latency the
    customer actually feels.

    "Reply with ONLY that one word" plus .strip().lower() is the cheap version
    of structured output. For a two-way choice it's enough; when the enum
    grows or a wrong route becomes expensive, force a tool call instead (the
    pattern used in AM_H1's extract_slot_value).
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=10,
        system=(
            "Classify the customer message as exactly one word: either "
            "'claims' (filing or checking status of a claim) or 'policy' "
            "(coverage/policy wording questions). Reply with ONLY that one word."
        ),
        messages=[{"role": "user", "content": message}],
    )
    return _text(response).strip().lower()


# ---------- 2. The specialists ----------
#
# Note what each one is NOT given. The claims specialist never sees the policy
# clauses, so it cannot answer a coverage question by improvising — the scope
# limit is structural, not just an instruction it might ignore.

def claims_specialist_reply(message: str) -> str:
    claims_context = json.dumps(DATA["claims"], indent=2)
    system = f"""You are a Claims Specialist for an insurance company. You are
empathetic and focused on claim status and next steps. Here is the claims
data you have access to:

{claims_context}

If asked a general policy coverage question, say that's outside what you
handle and that you can transfer them to the Policy team."""
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        messages=[{"role": "user", "content": message}],
    )
    return _text(response)


def policy_specialist_reply(message: str) -> str:
    # Clauses are rendered with their ids inline ("[POL-010] Roadside...") so
    # the model has something concrete to cite. Ask for citations without
    # putting ids in the context and it will invent plausible-looking ones.
    clauses_context = "\n\n".join(
        f"[{c['id']}] {c['title']}\n{c['text']}" for c in DATA["policy_clauses"]
    )
    system = f"""You are a Policy Specialist for an insurance company. You are
precise and citation-oriented. Answer ONLY using the policy clauses below,
citing the clause id (e.g. [POL-010]) for every factual claim. If the answer
isn't in these clauses, say you don't have that information rather than
guessing. If asked about claim status, say that's outside what you handle.

{clauses_context}"""
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        messages=[{"role": "user", "content": message}],
    )
    return _text(response)


# ---------- 3. The router ----------

def route_and_respond(message: str):
    """Returns (specialist_name, reply).

    Returning the name alongside the reply is not cosmetic — it's the audit
    trail. In production this is what you log and what you chart when someone
    asks "why did the customer get that answer?". Routing decisions are the
    first thing that silently degrades, and you can't measure what you don't
    record.

    The `else` catches anything that isn't exactly "claims" — including a
    classifier that returns "Claims." or a surprise third word. Defaulting to
    policy is a deliberate, if blunt, choice; a real system would validate the
    label against a known set and escalate on an unrecognized one.
    """
    intent = classify_intent(message)
    if intent == "claims":
        return "Claims Specialist", claims_specialist_reply(message)
    else:
        return "Policy Specialist", policy_specialist_reply(message)


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

# Expected: msg 1 -> Claims Specialist, references CLM-3391 status/next step.
# msg 2 -> Policy Specialist, cites POL-010 (roadside assistance).
# msg 3 -> Policy Specialist, cites POL-011 (sudden plumbing failure covered).
