r"""
PM · H3 — Telecom Channel Adapters with Shared State (REFERENCE SOLUTION)

THE PATTERN: normalize at the edge, format at the edge, one core in between.

    chat message  --adapt_chat--\                    /--format_for_chat--> chat
                                 >-- handle_message -<
    email         --adapt_email-/                    \--format_for_email-> email

handle_message() reads normalized_message["text"] and never looks at
["channel"]. That's not a stylistic preference — it's the whole exercise.

The alternative everyone builds first is one agent per channel: a chat bot and
an email bot. They drift within weeks. A policy fix lands in one and not the
other, and worst of all their memory is separate, so a customer who explains
their problem over chat explains it again over email. This lab's payoff is at
the bottom of the file: the plan mentioned in the chat message is already
known when the email arrives, and no code was written to make that happen.

The channel field is still carried through — for logging and routing the
reply. It just never influences what the agent DECIDES. Tone and greeting are
presentation, applied on the way out by the formatters.

Adding SMS is then: one adapter, one formatter, zero changes to the core.
"""

import json
import os
import sys
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

    Do NOT write response.content[0].text. content[0] is often a
    ThinkingBlock — the model reasoning before it answers — and ThinkingBlock
    has no .text attribute, so that shortcut dies with a confusing
    AttributeError. It only happens on some turns, which is what makes it
    nasty: it passes in testing and fails later. Always search by block type.
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


# ---------- Channel adapters: many shapes in, one shape out ----------
#
# Every adapter returns the SAME three keys regardless of what the channel
# natively looks like. Channel-specific structure is flattened here, at the
# edge, so it never reaches the core.

def adapt_chat(customer_id: str, message: str) -> dict:
    # Chat is already the normal form — the adapter is trivial, and that's
    # fine. Its value is that the core has exactly one input shape to handle.
    return {"customer_id": customer_id, "channel": "chat", "text": message}


def adapt_email(customer_id: str, subject: str, body: str) -> dict:
    # Email has a field chat doesn't. Rather than teaching the core about
    # subject lines, fold it into text — subjects often carry the actual
    # intent ("Billing question"), so dropping it would lose information.
    return {"customer_id": customer_id, "channel": "email", "text": f"Subject: {subject}\n\n{body}"}


# ---------- Channel-agnostic core ----------

def handle_message(normalized_message: dict) -> str:
    """The one agent. Note what is NOT read here: ["channel"].

    Every `if channel == ...` you add to this function is a place where the
    channels can drift apart. Behavior that genuinely differs by channel
    belongs in an adapter (going in) or a formatter (coming out), never here.
    """
    customer_id = normalized_message["customer_id"]
    text = normalized_message["text"]

    # Keyed by CUSTOMER, not by customer+channel. This single choice is what
    # makes cross-channel memory work: chat and email are the same person, so
    # they read and write the same profile. Key it by session or by channel
    # and you've rebuilt the silo you were trying to avoid.
    profile = load_profile(customer_id)
    if profile:
        known = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        system = (
            "You are a telecom support agent. Known facts about this "
            f"customer:\n{known}\n\nDo not re-ask for any of the above."
        )
    else:
        system = "You are a telecom support agent."

    # Generous budget: a reply cut off mid-sentence looks exactly like the
    # agent forgetting something, which makes the cross-channel payoff below
    # impossible to read.
    response = client.messages.create(
        model=MODEL, max_tokens=700, system=system,
        messages=[{"role": "user", "content": text}],
    )
    reply = _text(response)

    for k, v in extract_facts(text).items():
        save_fact(customer_id, k, v)

    return reply


# ---------- Response formatters: one shape in, many shapes out ----------
#
# Presentation only. These change how the answer LOOKS, never what it says —
# which is why they take a plain string and can be tested without an API key.
# Channel etiquette (greetings, sign-offs, SMS length limits, markdown vs
# plain text) all lives at this layer.

def format_for_chat(reply: str) -> str:
    # Passthrough. Kept as a function anyway so every channel goes through the
    # same pipeline shape — the day chat needs length-capping, there's an
    # obvious place to put it.
    return reply


def format_for_email(reply: str) -> str:
    # Email convention the model was never told about. Keeping it out of the
    # prompt means one less channel-specific instruction competing for the
    # model's attention, and it's deterministic.
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
