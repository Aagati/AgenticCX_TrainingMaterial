r"""
PM · H3 — Telecom Channel Adapters with Shared State (STARTER)

    chat  --adapt_chat--\                    /--format_for_chat--> chat
                         >-- handle_message -<
    email --adapt_email-/                    \--format_for_email-> email

The rule that makes this work: handle_message() must never read
normalized_message["channel"]. Every `if channel == ...` inside the core is a
place where your chat experience and your email experience can drift apart —
a policy fix lands in one and not the other.

The alternative most teams build first is one agent per channel. They diverge
within weeks, and worse, their memory is separate: a customer explains the
problem over chat, then explains it again over email. The payoff you're
building toward is at the bottom of this file — the plan mentioned over chat
should already be known when the email arrives, with no code written to make
that happen.

Things that DO differ by channel are still handled, just not in the core:
structure on the way in (adapters), tone and sign-off on the way out
(formatters). Adding SMS should then be one adapter, one formatter, and zero
changes to handle_message().

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


def _text(response) -> str:
    """Provided — use this instead of response.content[0].text in TODO 3.

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
    # "Reply with ONLY valid JSON, no markdown fences" is an instruction, not
    # a guarantee — the model wraps its answer in ```json fences often enough
    # that skipping this step makes extraction return {} on most turns and the
    # entire memory feature silently does nothing. Strip fences, THEN parse.
    text = _text(response).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}  # learned nothing this turn — never crash the conversation


# ---------- Channel adapters (TODO 1 & 2) ----------

def adapt_chat(customer_id: str, message: str) -> dict:
    """TODO 1: Return {"customer_id":..., "channel":"chat", "text": message}."""
    raise NotImplementedError


def adapt_email(customer_id: str, subject: str, body: str) -> dict:
    """
    TODO 2: Combine subject + body into one text field, e.g.
    f"Subject: {subject}\\n\\n{body}", and return the normalized schema
    with "channel": "email".

    Fold the subject in rather than dropping it or adding a fourth key.
    Subjects often carry the actual intent ("Billing question"), and adding a
    key only email has would push channel-awareness into the core — exactly
    what this design is avoiding.
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

    load_profile is keyed by CUSTOMER, not customer+channel. That one choice
    is what makes cross-channel memory work — chat and email are the same
    person, so they read and write the same profile. Key it by session or
    channel and you've rebuilt the silo.

    Also resist putting "keep it brief, this is chat" in the system prompt.
    That's presentation, it belongs in a formatter, and the moment it's in the
    prompt the core is channel-aware again.
    """
    raise NotImplementedError


# ---------- Response formatters (TODO 4) ----------

def format_for_chat(reply: str) -> str:
    """TODO 4a: Chat formatting is a passthrough — just return reply.

    Yes, this is a function that does nothing. Keep it anyway: every channel
    then goes through the same pipeline shape, so the day chat needs length
    capping there's an obvious place to put it.
    """
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
