"""
PM · H2 — Banking Episodic + Semantic Memory (REFERENCE SOLUTION)
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
    store = _load_store()
    cust = _get_customer(store, customer_id)
    cust["semantic"][key] = value
    _write_store(store)


def load_semantic(customer_id: str) -> dict:
    store = _load_store()
    return store.get(customer_id, {}).get("semantic", {})


def add_episode(customer_id: str, summary: str):
    store = _load_store()
    cust = _get_customer(store, customer_id)
    cust["episodic"].append({"date": date.today().isoformat(), "summary": summary})
    _write_store(store)


def load_recent_episodes(customer_id: str, n: int = 3) -> list:
    store = _load_store()
    episodes = store.get(customer_id, {}).get("episodic", [])
    return episodes[-n:]


def extract_semantic_facts(message: str) -> dict:
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
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system="Summarize this customer service exchange in ONE short sentence, third person.",
        messages=[{"role": "user", "content": f"Customer: {customer_message}\nAgent: {agent_reply}"}],
    )
    return response.content[0].text.strip()


def chat(customer_id: str, message: str) -> str:
    semantic = load_semantic(customer_id)
    episodes = load_recent_episodes(customer_id)

    parts = ["You are a banking support agent."]
    if semantic:
        known = "\n".join(f"- {k}: {v}" for k, v in semantic.items())
        parts.append(f"Known facts about this customer:\n{known}")
    if episodes:
        history = "\n".join(f"- {e['date']}: {e['summary']}" for e in episodes)
        parts.append(f"Recent history with this customer:\n{history}")
    parts.append("Do not re-ask for known facts. Reference recent history naturally when relevant.")
    system = "\n\n".join(parts)

    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system,
        messages=[{"role": "user", "content": message}],
    )
    reply = response.content[0].text

    for k, v in extract_semantic_facts(message).items():
        save_semantic_fact(customer_id, k, v)
    add_episode(customer_id, summarize_episode(message, reply))

    return reply


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

    print("\n=== SESSION 3 ===")
    m3 = "Also, what's my account balance?"
    print("CUSTOMER:", m3)
    print("AGENT:", chat(cid, m3))

    print("\n[Full memory store]:")
    print(json.dumps(_load_store(), indent=2))

# Expected: semantic picks up preferred_name "Priya". Episodic accumulates
# 3 entries. Session 2's reply should reference the Green Leaf Grocers
# dispute from episodic memory without the customer restating it.
