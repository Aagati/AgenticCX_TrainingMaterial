"""
PM · H3 — Telecom Channel Adapters with Shared State (STARTER)
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


# ---------- Channel adapters (TODO 1 & 2) ----------

def adapt_chat(customer_id: str, message: str) -> dict:
    """TODO 1: Return {"customer_id":..., "channel":"chat", "text": message}."""
    raise NotImplementedError


def adapt_email(customer_id: str, subject: str, body: str) -> dict:
    """
    TODO 2: Combine subject + body into one text field, e.g.
    f"Subject: {subject}\\n\\n{body}", and return the normalized schema
    with "channel": "email".
    """
    raise NotImplementedError


# ---------- Channel-agnostic core (TODO 3) ----------

def handle_message(normalized_message: dict) -> str:
    """
    TODO 3: This function must NOT branch on normalized_message["channel"].
    It should:
      1. Load the customer's profile via load_profile().
      2. Build a system prompt including known facts (if any).
      3. Call Claude with normalized_message["text"] as the user message.
      4. Extract + save any new facts.
      5. Return the raw reply text (formatting for the channel happens
         OUTSIDE this function, in the formatters below).
    """
    raise NotImplementedError


# ---------- Response formatters (TODO 4) ----------

def format_for_chat(reply: str) -> str:
    """TODO 4a: Chat formatting is a passthrough — just return reply."""
    raise NotImplementedError


def format_for_email(reply: str) -> str:
    """
    TODO 4b: Wrap `reply` with an email-appropriate greeting and sign-off,
    e.g. "Hi,\\n\\n{reply}\\n\\nBest regards,\\nSupport Team"
    """
    raise NotImplementedError


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
    print("\n(Check: did the email reply reference the plan mentioned over chat, without re-asking?)")
