"""
AM · H2 — Insurance Supervisor Routing (REFERENCE SOLUTION)
"""

import json
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("mock_data.json") as f:
    DATA = json.load(f)


def classify_intent(message: str) -> str:
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
    return response.content[0].text.strip().lower()


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
    return response.content[0].text


def policy_specialist_reply(message: str) -> str:
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
    return response.content[0].text


def route_and_respond(message: str):
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
