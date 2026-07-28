"""
AM · H3 — Telecom Cross-Session Memory (STARTER)

Design note: within ONE conversation, "don't make the customer repeat
themselves" is free — the message history does it for you. Across sessions it
is an engineering decision, and that decision is this lab. Note that neither
chat() call below passes any conversation history; the ONLY thing carrying
information from session 1 to session 2 is what you chose to write to disk.

The hard part is not the JSON file — it's extract_facts() deciding what
deserves to persist. "I'm on a Pixel 9a" is durable. "My data is slow today"
is not, and a system that saves it will still be bringing up a fixed outage
months from now. That judgment call is the discussion at the end.

Run it from this directory: `python starter.py`
"""

import json
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from the repo-root .env

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

    Wrap json.loads in try/except and return {} on failure. "Reply with ONLY
    JSON" is an instruction, not a guarantee — a stray ```json fence or a
    "Here's the JSON:" preamble will land you in JSONDecodeError, and a
    crashed extraction should degrade to "learned nothing this turn", not
    take down the whole conversation.
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

    Order matters in a way that's easy to miss: load the profile BEFORE
    calling the model, and extract facts AFTER. Facts learned from this
    message are for the NEXT session — the model already has this message in
    full, so re-injecting them now buys nothing.

    Give the reply room (max_tokens ~800). If the reply gets cut off
    mid-sentence, the fact you were checking for may simply be in the part
    that never got generated — which looks exactly like a memory failure and
    isn't one.
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

# Grading your own recall is harder than it looks. Resist writing
#     assert "Unlimited Plus" in reply
# — the agent may remember perfectly and still say "your current plan", and a
# truncated reply fails the same test for an unrelated reason. See
# solution.py's check_recall() for the tiered version: exact match, then token
# overlap, then an LLM judge that can tell "paraphrased it", "didn't need it",
# and "re-asked for it" apart. Only that last one is a real failure.
