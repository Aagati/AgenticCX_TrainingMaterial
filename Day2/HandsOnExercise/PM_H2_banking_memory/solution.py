"""
PM · H2 — Banking Episodic + Semantic Memory (REFERENCE SOLUTION)

THE PATTERN: two kinds of memory, because they behave differently.

  SEMANTIC — timeless facts about WHO the customer is.
             "prefers to be called Priya." Overwrite on change, keep forever,
             load all of it every turn. A dict.

  EPISODIC — dated events, WHAT happened.
             "2026-07-28: disputed a $45 charge." Append-only, never edited,
             load only the recent tail. A list.

AM · H3 had only the semantic half, and it couldn't answer "any update on
that dispute I filed?" — nothing durable was said in that sentence, so a
profile store has nothing to retrieve. The episodic log is what makes the
follow-up work.

Why not one big store? Because the two need opposite retrieval. Semantic
facts must ALL be present or the agent re-asks something it was told. Episodes
grow without limit, so you must select — and "the last 3" is the crudest
version of that selection. Merge them and you're forced to pick one policy for
both, which is wrong for one of them.

    load_semantic()         -> everything
    load_recent_episodes()  -> the tail only
"""

import json
import os
import sys
from datetime import date
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

# Windows consoles default to cp1252 and crash when the model emits an arrow,
# em-dash or curly quote. Force UTF-8 so a print() cannot kill the lab.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = Anthropic()
MODEL = "claude-sonnet-5"

# Keep the store next to THIS file, not in whatever directory you happened
# to launch from — otherwise "delete it for a clean slate" hits the wrong
# file and the memory demo looks broken.
STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store.json")


def _text(response) -> str:
    """Pull the reply text out of a response.

    Do NOT write _text(response). content[0] is often a
    ThinkingBlock — the model reasoning before it answers — and ThinkingBlock
    has no .text attribute, so that shortcut dies with a confusing
    AttributeError. It only happens on some turns, which is what makes it
    nasty: it passes in testing and fails later. Always search by block type.
    """
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


# Shape on disk, per customer:
#   {"cust_5510": {"semantic": {...},           <- dict, overwritten
#                  "episodic": [{date, summary}]}}  <- list, appended
# One file with two sections, because they're read on different schedules.


def _load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH) as f:
        return json.load(f)


def _write_store(store: dict):
    with open(STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def _get_customer(store: dict, customer_id: str) -> dict:
    # setdefault creates the two-section skeleton on first contact, so every
    # writer below can assume both keys exist.
    return store.setdefault(customer_id, {"semantic": {}, "episodic": []})


# ---------- Semantic: facts, overwritten in place ----------

def save_semantic_fact(customer_id: str, key: str, value: str):
    # Assignment, not append — the newest value for a key replaces the old
    # one. A customer who changes their phone number has ONE phone number,
    # and keeping the history here would mean the agent reads out both.
    store = _load_store()
    cust = _get_customer(store, customer_id)
    cust["semantic"][key] = value
    _write_store(store)


def load_semantic(customer_id: str) -> dict:
    store = _load_store()
    return store.get(customer_id, {}).get("semantic", {})


# ---------- Episodic: events, appended forever ----------

def add_episode(customer_id: str, summary: str):
    # Append, never overwrite. Each episode is stamped with its date, because
    # "disputed a charge" means something different last week than last year —
    # recency is part of the fact.
    store = _load_store()
    cust = _get_customer(store, customer_id)
    cust["episodic"].append({"date": date.today().isoformat(), "summary": summary})
    _write_store(store)


def load_recent_episodes(customer_id: str, n: int = 3) -> list:
    """The tail, not the whole list.

    This cap is the entire reason episodic memory is separate. A five-year
    customer has hundreds of episodes; injecting them all would blow the
    context window, cost a fortune per turn, and bury the relevant one in
    noise. Recency is the cheapest useful relevance heuristic — a production
    system would rank by embedding similarity to the current message instead,
    but the principle is the same: SELECT, don't dump.
    """
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
    """Compress a whole exchange into one line before storing it.

    Storing raw transcripts would defeat the purpose — you'd be back to
    unbounded context. max_tokens=60 enforces the compression budget: an
    episode has to earn its place in a future prompt in one sentence.

    Cost note: this makes THREE model calls per turn (reply + fact extraction
    + summary). Fine for a lab. In production you'd summarize on session end
    rather than per message, or batch it out of the response path entirely —
    the customer is waiting on the reply, not on the bookkeeping.
    """
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system="Summarize this customer service exchange in ONE short sentence, third person.",
        messages=[{"role": "user", "content": f"Customer: {customer_message}\nAgent: {agent_reply}"}],
    )
    return _text(response).strip()


def chat(customer_id: str, message: str) -> str:
    semantic = load_semantic(customer_id)
    episodes = load_recent_episodes(customer_id)

    # Two LABELED sections, not one merged blob. The labels matter: the model
    # needs to know that "prefers Priya" is currently true while "disputed a
    # charge on the 10th" is something that happened. Flatten them together
    # and you get an agent that treats a stale event as a present fact.
    parts = ["You are a banking support agent."]
    if semantic:
        known = "\n".join(f"- {k}: {v}" for k, v in semantic.items())
        parts.append(f"Known facts about this customer:\n{known}")
    if episodes:
        # Dates are included deliberately — they let the model calibrate
        # ("earlier today" vs "back in March") instead of treating every
        # episode as equally fresh.
        history = "\n".join(f"- {e['date']}: {e['summary']}" for e in episodes)
        parts.append(f"Recent history with this customer:\n{history}")
    # Different instruction per memory type: facts must not be re-asked;
    # history should be referenced only "when relevant". An agent that recites
    # your history back at you every turn is unsettling, not helpful.
    parts.append("Do not re-ask for known facts. Reference recent history naturally when relevant.")
    system = "\n\n".join(parts)

    # Generous budget: a reply cut off mid-sentence looks exactly like the
    # agent having forgotten something, which makes the memory payoff in
    # session 2 impossible to read.
    response = client.messages.create(
        model=MODEL, max_tokens=700, system=system,
        messages=[{"role": "user", "content": message}],
    )
    reply = _text(response)

    # Write-back happens AFTER the reply. Both stores are updated from this
    # turn for the benefit of the NEXT one — the model already had this
    # message in full, so nothing here changes the answer just given.
    for k, v in extract_semantic_facts(message).items():
        save_semantic_fact(customer_id, k, v)
    # Note the episode summarizes BOTH sides. "Customer asked about a charge"
    # loses the outcome; what makes session 2 work is knowing what the agent
    # said it would do.
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
