"""
AM · H3 — Telecom Cross-Session Memory (STARTER)
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
    """TODO 1: Load the store, set store[customer_id][key] = value, write it back."""
    raise NotImplementedError


def load_profile(customer_id: str) -> dict:
    """TODO 2: Return the dict of known facts for customer_id (empty dict if none)."""
    raise NotImplementedError


def extract_facts(message: str) -> dict:
    """
    TODO 3: Use a narrow Claude call to extract DURABLE profile facts from
    `message` as a JSON object, e.g. {"device": "iPhone 15", "plan": "Unlimited Plus"}.
    Only include keys the message actually mentions. Instruct the model to
    reply with ONLY valid JSON (no markdown fences). Parse and return the dict
    (return {} if parsing fails or nothing durable was mentioned).
    """
    raise NotImplementedError


def chat(customer_id: str, message: str) -> str:
    """
    TODO 4:
      1. Load the customer's existing profile.
      2. Build a system prompt that includes known facts (if any) and
         instructs the agent not to re-ask for anything already known.
      3. Call Claude for a reply.
      4. Extract any new durable facts from `message` and save them.
      5. Return the reply text.
    """
    raise NotImplementedError


if __name__ == "__main__":
    cid = "cust_8842"

    print("=== SESSION 1 ===")
    print("CUSTOMER: Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan.")
    print("AGENT:", chat(cid, "Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan."))

    print("\n=== SESSION 2 (next day, new conversation) ===")
    print("CUSTOMER: Hey, I have a question about my bill.")
    print("AGENT:", chat(cid, "Hey, I have a question about my bill."))
    print("\n(Check: did the agent need to re-ask for device/plan? It shouldn't have.)")
