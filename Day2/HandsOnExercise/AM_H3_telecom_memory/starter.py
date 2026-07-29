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

Run: `python starter.py` — paths resolve relative to this file, so any
working directory is fine.
"""

import json
import os
import re
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
#JUDGE_MODEL=...


# Keep the store next to THIS file, not in whatever directory you happened
# to launch from — otherwise "delete it for a clean slate" hits the wrong
# file and the memory demo looks broken.
STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store.json")


def _load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH) as f:
        return json.load(f)


def _write_store(store: dict):
    with open(STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


class Reply(str):
    """Provided — needed for the BONUS recall check near the bottom of this
    file. A plain str subclass that also carries why generation stopped, so
    a truncated reply ("ran out of tokens") isn't graded the same as a
    forgotten fact. Behaves like a normal string everywhere else (print(),
    "in" checks, f-strings all just work)."""

    def __new__(cls, text: str, stop_reason: str = "end_turn"):
        obj = super().__new__(cls, text)
        obj.stop_reason = stop_reason
        return obj


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

    "Reply with ONLY JSON" is an instruction, not a guarantee — defend
    against the two ways models break it, before you ever call json.loads:
      1. A ```json ... ``` fence around the object — strip a leading
         ```(json)? and a trailing ``` first.
      2. A prose preamble ("Here's the JSON:") ahead of the object — if the
         direct parse still throws, regex out the first {...} substring and
         try parsing that instead.
    Wrap the whole thing in try/except json.JSONDecodeError and return {} on
    failure either way. A crashed extraction should degrade to "learned
    nothing this turn," not take down the whole conversation.
    """
    raise NotImplementedError


def chat(customer_id: str, message: str) -> Reply:
    """
    TODO 4:
      1. Load the customer's existing profile.
      2. Build a system prompt that includes known facts (if any) and
         instructs the agent not to re-ask for anything already known.
      3. Call Claude for a reply.
      4. Extract any new durable facts from `message` and save them.
      5. Return Reply(text, response.stop_reason) — not a plain string. It
         behaves like one everywhere (print, f-strings, "in"), but carries
         stop_reason for the BONUS recall check below.

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


# ==========================================================================
# BONUS (optional — not required to complete the core lab above)
#
# Grading your own recall is harder than it looks. Resist writing
#     assert "Unlimited Plus" in reply
# — the agent may remember perfectly and still say "your current plan", and a
# truncated reply fails the same test for an unrelated reason. This section
# builds a tiered check instead: exact match, then token overlap, then an
# LLM judge that can tell "paraphrased it", "didn't need it", and "re-asked
# for it" apart. Only that last one is a real failure.
# ==========================================================================

_STOPWORDS = {"a", "an", "the", "with", "and", "or", "of", "for", "on", "in",
              "my", "your", "per", "is", "to", "at"}

_TIER2_COVERAGE = 0.8  # fraction of a fact's distinctive tokens that must appear

# Verdicts the judge can return that mean the memory layer actually failed.
_GENUINE_FAILURES = {"re_asked", "contradicted", "missing"}

_JUDGE_SYSTEM = """You grade whether a support agent's reply shows it REMEMBERED a stored customer fact.
You are NOT grading tone, helpfulness, or whether the advice is correct.

You receive: the stored fact, the customer's message, and the agent's reply.

Reply with ONLY a JSON object: {"verdict": "<one below>", "why": "<12 words max>"}

- "recalled"       - the reply uses the fact, verbatim or paraphrased, or is plainly written knowing it
- "not_applicable" - the fact is irrelevant to what the customer asked; not using it is correct
- "re_asked"       - the reply asks the customer for this fact, which it should already know
- "contradicted"   - the reply states something inconsistent with the stored fact
- "missing"        - the fact was clearly relevant, but the reply neither used nor acknowledged it

When unsure whether the fact was relevant, prefer "not_applicable" over "missing".
A generic reference ("your plan", "your device") counts as "recalled" only if the
surrounding content is specific to the stored value; otherwise judge on the whole reply."""


# Provided — plumbing for the tiers below, not the lesson itself.
def _normalize(text: str) -> str:
    return " ".join(t for t in re.split(r"[^a-z0-9]+", text.lower()) if t)


def _tokens(text: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower())
            if t and t not in _STOPWORDS}


def _token_coverage(value: str, reply: str) -> float:
    wanted = _tokens(value)
    if not wanted:
        return 0.0
    return len(wanted & _tokens(reply)) / len(wanted)


def judge_recall(key: str, value: str, question: str, reply: str) -> dict:
    """
    TODO 5 (BONUS): LLM-as-judge fallback for anything the tier-1/tier-2
    string checks in check_recall() (TODO 6) can't settle — paraphrase,
    omission, irrelevance.

    Call Claude with system=_JUDGE_SYSTEM and a user message containing the
    stored fact (key/value), the customer's message, and the agent's reply.
    Parse the JSON response the same defensive way as TODO 3 — a judge call
    that throws or returns junk should degrade to
    {"verdict": "inconclusive", "why": "..."}, not crash the grading run.
    Validate the returned verdict is one of _GENUINE_FAILURES | {"recalled",
    "not_applicable"} before trusting it; if not, that's also "inconclusive".
    """
    raise NotImplementedError


def check_recall(key: str, value: str, question: str, reply: Reply) -> dict:
    """
    TODO 6 (BONUS): Grade one stored fact against one reply. Return a dict
    like {"status": "PASS", "detail": "..."}. status is one of:
      PASS         - the agent demonstrably used the fact
      SKIP         - the fact wasn't relevant to this question; nothing to prove
      FAIL         - genuine memory failure (re-asked, contradicted, or ignored)
      INCONCLUSIVE - the reply was truncated, or the judge couldn't decide
      INVALID      - the customer restated the fact, so recall wasn't tested

    Tiers, cheapest first:
      0. If _token_coverage(value, question) >= _TIER2_COVERAGE, the customer
         handed the fact back in THIS message — recall isn't being tested.
         -> INVALID
      1. If _normalize(value) is a substring of _normalize(reply) -> PASS
         (stated verbatim).
      2. If _token_coverage(value, reply) >= _TIER2_COVERAGE -> PASS
         (near-verbatim).
      3. Otherwise call judge_recall() (TODO 5) and map its verdict:
         "recalled" -> PASS, "not_applicable" -> SKIP, "inconclusive" -> stays
         INCONCLUSIVE. Any of _GENUINE_FAILURES -> FAIL, UNLESS
         reply.stop_reason == "max_tokens", in which case a missing fact is
         attributable to truncation, not memory -> INCONCLUSIVE instead.
    """
    raise NotImplementedError


if __name__ == "__main__":
    cid = "cust_8842"

    print("=== SESSION 1 ===")
    msg1 = "Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan."
    print("CUSTOMER:", msg1)
    print("AGENT:", chat(cid, msg1))

    print("\n=== SESSION 2 (next day, new conversation) ===")
    msg2 = "Hey, I have a question about my bill."
    print("CUSTOMER:", msg2)
    reply2 = chat(cid, msg2)
    print("AGENT:", reply2)
    print("\n(Check: did the agent need to re-ask for device/plan? It shouldn't have.)")

    # BONUS: once TODO 5 + TODO 6 are implemented, grade the recall for real
    # instead of eyeballing the transcript above.
    # profile = load_profile(cid)
    # for key, value in profile.items():
    #     result = check_recall(key, value, msg2, reply2)
    #     print(f"  {result['status']} — {key}={value!r}: {result['detail']}")
