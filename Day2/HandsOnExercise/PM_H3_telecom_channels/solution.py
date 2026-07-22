"""
PM · H3 — Telecom Channel Adapters with Shared State (REFERENCE SOLUTION)
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
    return _load_store().get(customer_id, {})


def extract_facts(message: str) -> dict:
    response = client.messages.create(
        model=MODEL, max_tokens=200,
        system=(
            "Extract DURABLE customer profile facts from this message as a JSON "
            "object. Reply with ONLY valid JSON, no markdown fences. If nothing "
            "durable is mentioned, reply with {}."
        ),
        messages=[{"role": "user", "content": message}],
    )
    try:
        return json.loads(response.content[0].text.strip())
    except json.JSONDecodeError:
        return {}


# ---------- Channel adapters ----------

def adapt_chat(customer_id: str, message: str) -> dict:
    return {"customer_id": customer_id, "channel": "chat", "text": message}


def adapt_email(customer_id: str, subject: str, body: str) -> dict:
    return {"customer_id": customer_id, "channel": "email", "text": f"Subject: {subject}\n\n{body}"}


# ---------- Channel-agnostic core ----------

def handle_message(normalized_message: dict) -> str:
    customer_id = normalized_message["customer_id"]
    text = normalized_message["text"]

    profile = load_profile(customer_id)
    if profile:
        known = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        system = (
            "You are a telecom support agent. Known facts about this "
            f"customer:\n{known}\n\nDo not re-ask for any of the above."
        )
    else:
        system = "You are a telecom support agent."

    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        messages=[{"role": "user", "content": text}],
    )
    reply = response.content[0].text

    for k, v in extract_facts(text).items():
        save_fact(customer_id, k, v)

    return reply


# ---------- Response formatters ----------

def format_for_chat(reply: str) -> str:
    return reply


def format_for_email(reply: str) -> str:
    return f"Hi,\n\n{reply}\n\nBest regards,\nSupport Team"


if __name__ == "__main__":
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)
    cid = "cust_7729"

    print("=== CHAT MESSAGE ===")
    chat_msg = adapt_chat(cid, "Hi, I'm on the Unlimited Plus plan and my WiFi calling keeps dropping.")
    reply1 = handle_message(chat_msg)
    print(format_for_chat(reply1))

    print("\n=== EMAIL MESSAGE (same customer, different channel) ===")
    email_msg = adapt_email(cid, "Billing question", "Hi, can you confirm my current plan and last bill amount?")
    reply2 = handle_message(email_msg)
    print(format_for_email(reply2))

    print("\n[memory_store.json]:", json.dumps(_load_store(), indent=2))
    print("\n(handle_message() never branched on channel — the plan fact saved from")
    print(" the chat message was available when handling the email, for free.)")
