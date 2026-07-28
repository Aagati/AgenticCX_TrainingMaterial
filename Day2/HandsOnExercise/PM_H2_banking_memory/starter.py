"""
PM · H2 — Banking Episodic + Semantic Memory (STARTER)

This morning's AM · H3 stored facts about WHO the customer is. That store
cannot answer session 2's question here — "any update on that dispute I
filed?" contains nothing durable to extract, so a profile store has nothing
to retrieve. What's missing is a record of what HAPPENED.

So: two stores, because they behave differently.

  SEMANTIC ("prefers to be called Priya")  — a dict. Overwrite on change,
      keep forever, load ALL of it every turn.
  EPISODIC ("2026-07-28: disputed a $45 charge") — a list. Append-only,
      never edited, load only the recent TAIL.

That last difference is the whole reason they're separate. Facts must all be
present or the agent re-asks something it was told. Episodes grow without
limit, so they must be selected. One store would force one retrieval policy
onto both, and it would be wrong for one of them.

Run it from this directory: `python starter.py`
"""

import json
import os
from datetime import date
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

client = Anthropic()
MODEL = "claude-sonnet-5"

STORE_PATH = "memory_store.json"


def _text(response) -> str:
    """Provided — use this instead of response.content[0].text in TODO 5.

    content[0] is often a ThinkingBlock (the model reasoning before it
    answers), and ThinkingBlock has no .text attribute. The shortcut dies with
    a confusing AttributeError — and only on some turns, so it passes while
    you're testing and fails later. Always search by block type.
    """
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


def _get_customer(store: dict, customer_id: str) -> dict:
    return store.setdefault(customer_id, {"semantic": {}, "episodic": []})


def save_semantic_fact(customer_id: str, key: str, value: str):
    """TODO 1: Set semantic[key] = value for this customer and persist.

    Assignment, not append — the newest value REPLACES the old one. A customer
    who changes their phone number has one phone number, and keeping both
    means the agent reads out both.
    """
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
    """TODO 4: Return the last n episodes for this customer (most recent last).

    The cap is the point, not a detail. A five-year customer has hundreds of
    episodes; injecting them all blows the context window, costs a fortune per
    turn, and buries the relevant one in noise. Recency is the crudest useful
    relevance heuristic — production ranks by similarity to the current
    message instead. Either way: SELECT, don't dump.
    """
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
    # "Reply with ONLY valid JSON, no markdown fences" is an instruction, not
    # a guarantee — the model wraps its answer in ```json fences often enough
    # that skipping this step makes extraction return {} on most turns and
    # semantic memory silently stays empty. Strip fences, THEN parse.
    text = _text(response).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}  # learned nothing this turn — never crash the conversation


def summarize_episode(customer_message: str, agent_reply: str) -> str:
    """Provided — a narrow call to produce a one-line episode summary."""
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system="Summarize this customer service exchange in ONE short sentence, third person.",
        messages=[{"role": "user", "content": f"Customer: {customer_message}\nAgent: {agent_reply}"}],
    )
    return _text(response).strip()


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

    Keep the two sections LABELED and separate in the system prompt. The model
    needs to know that "prefers Priya" is currently true while "disputed a
    charge on the 10th" is something that happened; flattened together, a
    stale event starts reading as a present fact. Include the dates for the
    same reason.

    Give them different instructions too. Facts: never re-ask. History:
    reference "when relevant" — an agent that recites your history back at you
    every turn is unsettling, not helpful.

    Steps 4 and 5 come AFTER the reply, on purpose: they're for the next
    session, and the model already had this message in full.
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
