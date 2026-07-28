"""
AM · H3 — Telecom Cross-Session Memory (REFERENCE SOLUTION)

The memory layer is the lab. The recall check below is the part most people
get wrong: an exact-substring test on generative output produces false
failures whenever the agent paraphrases a stored fact, whenever the reply is
cut off by max_tokens, and whenever the fact simply isn't relevant to what
the customer asked. This grades in tiers — cheap deterministic checks first,
an LLM judge only when those are inconclusive — and reserves a FAIL for a
genuine memory failure: the agent re-asked for a fact, contradicted it, or
ignored it when it clearly mattered.
"""

import json
import os
import re
import sys
import time

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv


load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"
JUDGE_MODEL = "claude-sonnet-5"

STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_store.json")

# Enough headroom that a multi-part answer finishes. A reply truncated
# mid-sentence is indistinguishable from a forgotten fact to a naive check.
REPLY_MAX_TOKENS = 800


# --------------------------------------------------------------------------
# API plumbing
# --------------------------------------------------------------------------

def _create(**kwargs):
    """messages.create with backoff, so a transient blip isn't graded as a
    memory failure."""
    for attempt in range(3):
        try:
            return client.messages.create(**kwargs)
        except (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        ):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def _text(response) -> str:
    """First text block's content — response.content[0] may be a
    ThinkingBlock (no .text) when the model reasons before replying."""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


class Reply(str):
    """Reply text that also carries why generation stopped. Lets the recall
    check tell 'ran out of tokens' apart from 'forgot the fact'."""

    def __new__(cls, text: str, stop_reason: str = "end_turn"):
        obj = super().__new__(cls, text)
        obj.stop_reason = stop_reason
        return obj


# --------------------------------------------------------------------------
# Memory store
# --------------------------------------------------------------------------

def _stringify(value) -> str:
    """extract_facts() can hand back nested values; the store and the system
    prompt both want flat strings."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {_stringify(v)}" for k, v in value.items())
    return str(value)


def _load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}  # corrupt or unreadable store — start clean rather than crash
    return data if isinstance(data, dict) else {}


def _write_store(store: dict):
    # Write-then-rename so an interrupted run can't leave a half-written store.
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, STORE_PATH)


def save_fact(customer_id: str, key: str, value):
    store = _load_store()
    store.setdefault(customer_id, {})[str(key)] = _stringify(value)
    _write_store(store)


def load_profile(customer_id: str) -> dict:
    store = _load_store()
    profile = store.get(customer_id, {})
    return profile if isinstance(profile, dict) else {}


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_object(text: str) -> dict:
    """Tolerate fences and stray prose around the JSON the model returns."""
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def extract_facts(message: str) -> dict:
    response = _create(
        model=MODEL,
        max_tokens=300,
        system=(
            "Extract DURABLE customer profile facts from this message as a "
            "JSON object — things like device model, plan name, or preferred "
            "contact method. Do NOT include one-off, session-specific details "
            "like 'data is slow today'. Reply with ONLY valid JSON, no markdown "
            "fences, no commentary. If nothing durable is mentioned, reply with {}."
        ),
        messages=[{"role": "user", "content": message}],
    )
    return _parse_json_object(_text(response).strip())


def chat(customer_id: str, message: str) -> Reply:
    profile = load_profile(customer_id)
    if profile:
        known = "\n".join(f"- {k}: {v}" for k, v in profile.items())
        system = (
            "You are a telecom support agent. Known facts about this "
            f"returning customer:\n{known}\n\n"
            "Do NOT re-ask for any of the above — use it naturally if relevant."
        )
    else:
        system = "You are a telecom support agent talking to a customer for the first time."

    response = _create(
        model=MODEL, max_tokens=REPLY_MAX_TOKENS, system=system,
        messages=[{"role": "user", "content": message}],
    )
    reply = Reply(_text(response), response.stop_reason)

    for k, v in extract_facts(message).items():
        save_fact(customer_id, k, v)

    return reply


# --------------------------------------------------------------------------
# Recall check
# --------------------------------------------------------------------------

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
    """LLM-as-judge fallback for anything the string checks can't settle."""
    payload = (
        f"STORED FACT: {key} = {value}\n\n"
        f"CUSTOMER MESSAGE:\n{question}\n\n"
        f"AGENT REPLY:\n{reply}"
    )
    try:
        # No temperature= here: it's deprecated on this model family and a 400
        # from the judge would silently turn every check INCONCLUSIVE.
        response = _create(
            model=JUDGE_MODEL,
            max_tokens=150,
            system=_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
        parsed = _parse_json_object(_text(response))
    except anthropic.APIError as exc:
        return {"verdict": "inconclusive", "why": f"judge call failed: {exc.__class__.__name__}"}

    verdict = str(parsed.get("verdict", "")).strip().lower()
    valid = _GENUINE_FAILURES | {"recalled", "not_applicable"}
    if verdict not in valid:
        return {"verdict": "inconclusive", "why": "judge returned an unusable verdict"}
    return {"verdict": verdict, "why": str(parsed.get("why", ""))[:80]}


def check_recall(key: str, value, question: str, reply: Reply) -> dict:
    """Grade one stored fact against one reply.

    status is one of:
      PASS         - the agent demonstrably used the fact
      SKIP         - the fact wasn't relevant to this question; nothing to prove
      FAIL         - genuine memory failure (re-asked, contradicted, or ignored)
      INCONCLUSIVE - the reply was truncated, or the judge couldn't decide
      INVALID      - the customer restated the fact, so recall wasn't tested
    """
    value = _stringify(value)
    truncated = getattr(reply, "stop_reason", "end_turn") == "max_tokens"

    if not value.strip():
        return {"status": "INVALID", "detail": "stored value is empty"}

    # The check only means something if the customer did NOT hand the fact back
    # to the agent in this message.
    if _token_coverage(value, question) >= _TIER2_COVERAGE:
        return {"status": "INVALID", "detail": "customer restated this fact — recall not exercised"}

    # Tier 1 — verbatim (punctuation- and case-insensitive).
    if _normalize(value) in _normalize(reply):
        return {"status": "PASS", "detail": "stated verbatim"}

    # Tier 2 — the fact's distinctive tokens are nearly all present.
    coverage = _token_coverage(value, reply)
    if coverage >= _TIER2_COVERAGE:
        return {"status": "PASS", "detail": f"{coverage:.0%} of fact tokens present"}

    # Tier 3 — paraphrase, omission, or irrelevance: ask a judge.
    verdict = judge_recall(key, value, question, reply)
    v, why = verdict["verdict"], verdict["why"]

    if v == "recalled":
        return {"status": "PASS", "detail": f"paraphrased — {why}"}
    if v == "not_applicable":
        return {"status": "SKIP", "detail": f"not relevant here — {why}"}
    if v == "inconclusive":
        return {"status": "INCONCLUSIVE", "detail": why}
    if truncated:
        # Fact absent, but the reply was cut off mid-thought — can't attribute
        # the absence to memory.
        return {"status": "INCONCLUSIVE", "detail": f"reply hit max_tokens — {why}"}
    return {"status": "FAIL", "detail": f"{v} — {why}"}


_ICONS = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP",
          "INCONCLUSIVE": "????", "INVALID": "n/a "}


if __name__ == "__main__":
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)  # clean slate for the demo

    cid = "cust_8842"
    failures = []

    print("=== SESSION 1 (customer states device + plan) ===")
    msg1 = ("Hi, my data has been really slow today. I'm on an Google Pixel 9a, "
            "Monthly plan with 2GB/day High speed data.")
    print("CUSTOMER:", msg1)
    print("AGENT:", chat(cid, msg1))

    profile = load_profile(cid)
    print(f"\n[{STORE_PATH} now contains]:", profile)

    if not profile:
        # Nothing was persisted — session 2 has nothing to recall, so grading it
        # would be meaningless. This is the real failure.
        print("\nFAIL — extract_facts() persisted nothing in session 1; memory layer is broken.")
        sys.exit(1)

    print("\n=== SESSION 2 (next day, new conversation — customer does NOT restate device/plan) ===")
    msg2 = "Hey, is my phone covered under device protection, and does my plan include international roaming?"
    print("CUSTOMER:", msg2)
    reply2 = chat(cid, msg2)
    print("AGENT:", reply2)
    if reply2.stop_reason == "max_tokens":
        print("\n[warning] reply hit max_tokens — raise REPLY_MAX_TOKENS for a clean read")

    print("\n=== RECALL CHECK ===")
    for key, value in profile.items():
        result = check_recall(key, value, msg2, reply2)
        print(f"  {_ICONS[result['status']]} — {key}={value!r}: {result['detail']}")
        if result["status"] == "FAIL":
            failures.append(key)

    if failures:
        print(f"\n{len(failures)} genuine memory failure(s): {', '.join(failures)}")
        sys.exit(1)
    print("\nNo genuine memory failures.")
