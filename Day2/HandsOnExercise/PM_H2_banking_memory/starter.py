"""
PM · H2 — Banking Episodic + Semantic Memory (STARTER)
"""

import json
import os
from datetime import date
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


def _get_customer(store: dict, customer_id: str) -> dict:
    return store.setdefault(customer_id, {"semantic": {}, "episodic": []})


def save_semantic_fact(customer_id: str, key: str, value: str):
    """TODO 1: Set semantic[key] = value for this customer and persist."""
    raise NotImplementedError


def load_semantic(customer_id: str) -> dict:
    """TODO 2: Return the semantic dict for this customer (empty if none)."""
    raise NotImplementedError


def add_episode(customer_id: str, summary: str):
    """
    TODO 3: Append {"date": <today's date as YYYY-MM-DD>, "summary": summary}
    to this customer's episodic list, and persist.
    """
    raise NotImplementedError


def load_recent_episodes(customer_id: str, n: int = 3) -> list:
    """TODO 4: Return the last n episodes for this customer (most recent last)."""
    raise NotImplementedError


def extract_semantic_facts(message: str) -> dict:
    """Provided — same pattern as this morning's extract_facts()."""
    response = client.messages.create(
        model=MODEL, max_tokens=200,
        system=(
            "Extract DURABLE customer profile facts from this message as a JSON "
            "object (e.g. preferred_name, communication_pref). Do NOT include "
            "one-off transactional details. Reply with ONLY valid JSON, no "
            "markdown fences. If nothing durable is mentioned, reply with {}."
        ),
        messages=[{"role": "user", "content": message}],
    )
    try:
        return json.loads(response.content[0].text.strip())
    except json.JSONDecodeError:
        return {}


def summarize_episode(customer_message: str, agent_reply: str) -> str:
    """Provided — a narrow call to produce a one-line episode summary."""
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system="Summarize this customer service exchange in ONE short sentence, third person.",
        messages=[{"role": "user", "content": f"Customer: {customer_message}\nAgent: {agent_reply}"}],
    )
    return response.content[0].text.strip()


def chat(customer_id: str, message: str) -> str:
    """
    TODO 5:
      1. Load semantic facts AND recent episodes for this customer.
      2. Build a system prompt with two clearly labeled sections: "Known
         facts about this customer" (semantic) and "Recent history" (episodic).
      3. Get a reply from Claude.
      4. Extract + save new semantic facts from `message`.
      5. Summarize this exchange and add_episode() it.
      6. Return the reply.
    """
    raise NotImplementedError


if __name__ == "__main__":
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)
    cid = "cust_5510"

    print("=== SESSION 1 ===")
    m1 = "Hi, I'm Priya. I'd like to dispute a $45 charge from Green Leaf Grocers on July 10th."
    print("CUSTOMER:", m1)
    print("AGENT:", chat(cid, m1))

    print("\n=== SESSION 2 ===")
    m2 = "Any update on that dispute I filed?"
    print("CUSTOMER:", m2)
    print("AGENT:", chat(cid, m2))
    print("(Check: did the agent reference the Green Leaf Grocers dispute from episodic memory?)")

    print("\n=== SESSION 3 ===")
    m3 = "Also, what's my account balance?"
    print("CUSTOMER:", m3)
    print("AGENT:", chat(cid, m3))
    print("\n[Full memory store]:", json.dumps(_load_store(), indent=2))
