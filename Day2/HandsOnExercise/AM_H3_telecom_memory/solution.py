"""
AM · H3 — Telecom Cross-Session Memory (REFERENCE SOLUTION)
"""

import json
import os
from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store.json")


def _text(response) -> str:
    """First text block's content — response.content[0] may be a
    ThinkingBlock (no .text) when the model reasons before replying."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


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
    text = _text(response).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
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
    reply = _text(response)

    new_facts = extract_facts(message)
    for k, v in new_facts.items():
        save_fact(customer_id, k, v)

    return reply


if __name__ == "__main__":
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)  # clean slate for the demo

    cid = "cust_8842"

    print("=== SESSION 1 (customer states device + plan) ===")
    msg1 = "Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan."
    print("CUSTOMER:", msg1)
    print("AGENT:", chat(cid, msg1))

    profile = load_profile(cid)
    print(f"\n[{STORE_PATH} now contains]:", profile)

    print("\n=== SESSION 2 (next day, new conversation — customer does NOT restate device/plan) ===")
    msg2 = "Hey, is my phone covered under device protection, and does my plan include international roaming?"
    print("CUSTOMER:", msg2)
    reply2 = chat(cid, msg2)
    print("AGENT:", reply2)

    print("\n=== RECALL CHECK ===")
    for key, value in profile.items():
        hit = value.lower() in reply2.lower()
        print(f"  {'PASS' if hit else 'FAIL'} — {key}={value!r} {'found' if hit else 'missing'} in session-2 reply")
