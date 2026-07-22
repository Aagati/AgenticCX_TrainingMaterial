"""
AM · H3 — Telecom Cross-Session Memory (REFERENCE SOLUTION)
"""

import json
import os
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

STORE_PATH = "memory_store.json"


def _load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH) as f:
        return json.load(f)


def _write_store(store: dict):
    with open(STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def save_fact(customer_id: str, key: str, value: str):
    store = _load_store()
    store.setdefault(customer_id, {})[key] = value
    _write_store(store)


def load_profile(customer_id: str) -> dict:
    store = _load_store()
    return store.get(customer_id, {})


def extract_facts(message: str) -> dict:
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=(
            "Extract DURABLE customer profile facts from this message as a "
            "JSON object — things like device model, plan name, or preferred "
            "contact method. Do NOT include one-off, session-specific details "
            "like 'data is slow today'. Reply with ONLY valid JSON, no markdown "
            "fences, no commentary. If nothing durable is mentioned, reply with {}."
        ),
        messages=[{"role": "user", "content": message}],
    )
    text = response.content[0].text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def chat(customer_id: str, message: str) -> str:
    profile = load_profile(customer_id)
    if profile:
        known = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        system = (
            "You are a telecom support agent. Known facts about this "
            f"returning customer:\n{known}\n\n"
            "Do NOT re-ask for any of the above — use it naturally if relevant."
        )
    else:
        system = "You are a telecom support agent talking to a customer for the first time."

    response = client.messages.create(
        model=MODEL, max_tokens=250, system=system,
        messages=[{"role": "user", "content": message}],
    )
    reply = response.content[0].text

    new_facts = extract_facts(message)
    for k, v in new_facts.items():
        save_fact(customer_id, k, v)

    return reply


if __name__ == "__main__":
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)  # clean slate for the demo

    cid = "cust_8842"

    print("=== SESSION 1 ===")
    msg1 = "Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan."
    print("CUSTOMER:", msg1)
    print("AGENT:", chat(cid, msg1))
    print("\n[memory_store.json now contains]:", load_profile(cid))

    print("\n=== SESSION 2 (next day, new conversation) ===")
    msg2 = "Hey, I have a question about my bill."
    print("CUSTOMER:", msg2)
    print("AGENT:", chat(cid, msg2))
    print("\n(Check: the agent's system prompt for session 2 already included "
          "device + plan from session 1 — the customer never had to restate them.)")
