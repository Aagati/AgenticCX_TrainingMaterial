"""
Lab-3: Retail - The Transcript Log Is Leaking Card Numbers (STARTER).

Self-paced, safe to skip entirely - most of this day's mechanics (layered
checks, persistent logs, policy-as-config) were already covered in Lab-1/
Lab-2. This lab is deliberately small: one new, contained idea, split into
two directions nobody should merge into one function - never STORE a
secret, and never SAY one.

You'll build:
  1. redact - five ordered patterns, findings that name what matched and
     never quote it.
  2. write_trace - the ONE function allowed to touch the log file,
     redacting every string in a record recursively before it's written.
  3. response_leak_check - the outbound direction: does the drafted reply
     itself leak a card/key, or another customer's email.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "redaction_patterns.json", encoding="utf-8") as f:
    PATTERNS = json.load(f)["patterns"]
with open(DATA_DIR / "retail_customers.json", encoding="utf-8") as f:
    CUSTOMERS = {c["customer_id"]: c for c in json.load(f)["customers"]}
with open(DATA_DIR / "support_transcripts.json", encoding="utf-8") as f:
    TRANSCRIPTS = json.load(f)["transcripts"]

TRACE_LOG_FILE = DATA_DIR / "redacted_trace_log.json"

_COMPILED_PATTERNS = [{"name": p["name"], "severity": p["severity"], "replacement": p["replacement"],
                        "regex": re.compile(p["pattern"])} for p in PATTERNS]


def draft_support_reply(transcript: dict, customer: dict) -> str:
    """Given - real MODEL_DRAFT call. Drafting is not this lab's idea; it's
    the thing the lab wraps."""
    turns_text = "\n".join(f"{t['role']}: {t['text']}" for t in transcript["turns"])
    response = Anthropic().messages.create(
        model=MODEL_DRAFT, max_tokens=350, thinking={"type": "disabled"},
        system=(
            "You write short retail support replies. Answer the customer's own pending question directly, "
            "in 1-2 sentences. Never invent or repeat back any card number, government id, api key, or "
            "another customer's contact details - if the transcript contains one, ignore it entirely."
        ),
        messages=[{"role": "user", "content": f"Customer: {customer['name']}\nTranscript:\n{turns_text}\n\nPending question: {transcript['pending_question']}"}],
    )
    return next(b for b in response.content if b.type == "text").text.strip()


def redact(text: str) -> tuple[str, list[dict]]:
    """
    TODO 1: Apply every pattern in _COMPILED_PATTERNS, in file order,
    substituting each match with that pattern's replacement token. Collect
    findings as a list of {"pattern": <name>, "severity": <severity>,
    "count": <how many matches that pattern made>} - one entry per pattern
    that matched at least once, and NOTHING for patterns that didn't.
    Return the redacted text and the findings. The findings must never
    carry the matched text, not even truncated: a findings list that
    quotes what it found is a second copy of the thing you were trying not
    to keep. Return findings as an empty list, not None, when nothing
    matched - several of these transcripts are clean and that is a real
    outcome.
    """
    raise NotImplementedError


def _redact_recursive(value, all_findings: list[dict]):
    """Given - walks a record recursively (strings inside lists inside
    dicts, which is where transcript turn text lives) so write_trace can
    redact every string in one pass regardless of shape."""
    if isinstance(value, str):
        redacted, findings = redact(value)
        all_findings.extend(findings)
        return redacted
    if isinstance(value, list):
        return [_redact_recursive(v, all_findings) for v in value]
    if isinstance(value, dict):
        return {k: _redact_recursive(v, all_findings) for k, v in value.items()}
    return value


def write_trace(record: dict, log_path: Path = TRACE_LOG_FILE) -> dict:
    """
    TODO 2: The persistence boundary - the ONE function allowed to touch
    redacted_trace_log.json. Use _redact_recursive (given) to redact every
    string value anywhere in `record`, accumulating every finding from
    every string into one findings list, and set the redacted record's
    "findings" key to that list. Load the existing log if present else
    start empty, append the redacted record, write back with indent=2, and
    return the redacted record you wrote. Redact on WRITE, never on read:
    a log that stores the raw value and masks it at display time is a log
    that leaks the moment someone reads the file instead of the UI - or the
    moment the file is what gets exfiltrated.
    """
    raise NotImplementedError


def response_leak_check(drafted_reply: str, customer: dict) -> dict:
    """
    TODO 3: The other direction. TODO 2 stops you STORING a secret; this
    stops you SAYING one. Scan `drafted_reply` for: any card_number or
    api_key match at all (never acceptable outbound, whoever it belongs
    to), and any email match that is NOT this customer's own email
    (customer["email"]) - leaking another customer's contact detail is the
    failure mode this guards against. Return {"safe": <bool>, "findings":
    [{"pattern": ..., "reason": ...}]} - again naming the pattern, never
    quoting the match. This check does not redact and does not rewrite: it
    reports, and the caller decides. That split is deliberate; automatic
    rewriting of a customer-facing message is a decision that deserves its
    own review, not a side effect of a scan.
    """
    raise NotImplementedError


def verify_log_clean(log_path: Path = TRACE_LOG_FILE) -> bool:
    """Given - re-reads the written file and asserts no raw pattern
    survives. Given so a student's own bug can't also write their own
    passing test."""
    if not log_path.exists():
        return True
    raw = json.dumps(json.load(open(log_path, encoding="utf-8")))
    for p in _COMPILED_PATTERNS:
        if p["regex"].search(raw):
            return False
    return True


def demo_response_leak() -> None:
    """Given - no live draft in this fixture happens to invent another
    customer's email or a raw card number, so response_leak_check's BLOCK
    path never fires in the main run. This proves it directly with a
    hand-crafted leaking reply."""
    print("\n=== Demo: response_leak_check catching an outbound leak ===")
    customer = CUSTOMERS["CUST-RT09"]
    leaking_reply = "Sure thing - for reference, a similar case was handled under jane.doe@example.com last week."
    result = response_leak_check(leaking_reply, customer)
    print(f"  Reply: \"{leaking_reply}\"")
    print(f"  safe={result['safe']} findings={result['findings']}")


if __name__ == "__main__":
    print(f"=== Lab-3: Retail Log Redaction — {len(TRANSCRIPTS)} transcripts ===\n")

    clean_count = 0
    for transcript in TRANSCRIPTS:
        customer = CUSTOMERS[transcript["customer_id"]]
        reply = draft_support_reply(transcript, customer)
        leak = response_leak_check(reply, customer)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "transcript_id": transcript["transcript_id"], "customer_id": transcript["customer_id"],
            "turns": transcript["turns"], "drafted_reply": reply, "response_leak_check": leak,
        }
        written = write_trace(record)
        if not written["findings"]:
            clean_count += 1
        print(f"  {transcript['transcript_id']} ({transcript['customer_id']}): "
              f"findings={written['findings']} leak_check_safe={leak['safe']}")

    print(f"\n--- Summary ---")
    print(f"  {clean_count}/{len(TRANSCRIPTS)} transcripts had zero findings")
    print(f"  Log verified clean (no raw pattern survives on disk): {verify_log_clean()}")

    demo_response_leak()
