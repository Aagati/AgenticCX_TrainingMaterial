"""
PM · H3 — Telecom Compliant Call Flow (STARTER)
"""

import json
from datetime import datetime, timezone
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

ERASURE_KEYWORDS = ["delete my data", "erase my recording", "forget this call", "delete my recording"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def disclose_ai(call_log: list):
    """
    TODO 1: Print the disclosure message the caller hears, e.g.
    "You're speaking with an AI assistant." Append a log entry to
    call_log: {"event": "disclosure_given", "timestamp": now_iso()}.
    """
    raise NotImplementedError


def request_recording_consent(call_log: list, caller_response: str):
    """
    TODO 2: Print a consent request. Treat caller_response as a refusal
    only if it contains "no" or "don't" (case-insensitive) — otherwise
    treat it as consent given. Append a log entry:
    {"event": "recording_consent", "granted": True/False, "timestamp": now_iso()}.
    Print whether the call will be recorded.
    """
    raise NotImplementedError


def check_erasure_request(text: str) -> bool:
    """TODO 3: Return True if text contains any phrase in ERASURE_KEYWORDS (case-insensitive)."""
    raise NotImplementedError


def call_llm(transcript: str) -> str:
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system="You are a telecom phone support agent. Reply in short, natural, spoken-style sentences. No markdown.",
        messages=[{"role": "user", "content": transcript}],
    )
    return response.content[0].text


def handle_speech(text: str, call_log: list) -> str:
    """
    TODO 4: If check_erasure_request(text) is True: print a confirmation
    to the caller that their erasure request will be honored, append
    {"event": "erasure_requested", "timestamp": now_iso(), "text": text}
    to call_log, and return early WITHOUT calling the LLM for a normal reply.
    Otherwise, call_llm(text), append {"event": "turn", "caller": text,
    "agent": reply, "timestamp": now_iso()} to call_log, print and return
    the reply.
    """
    raise NotImplementedError


def compliant_call_flow(events):
    """
    TODO 5: Iterate over `events`. Maintain call_log = []. On "answer",
    call disclose_ai() then request_recording_consent() (use the NEXT
    event's text as the caller_response if it's a "speech" event meant as
    the consent reply — for this lab, assume the event right after answer
    with type "consent_response" carries the caller's consent reply text).
    On "speech", call handle_speech(). On "hangup", stop. Print the full
    call_log as JSON at the end. Return call_log.
    """
    raise NotImplementedError


def simulate_call():
    yield {"type": "answer"}
    yield {"type": "consent_response", "text": "Sure, that's fine."}
    yield {"type": "speech", "text": "Hi, I want to check my data usage this month."}
    yield {"type": "speech", "text": "Actually, can you delete my data from this call?"}
    yield {"type": "speech", "text": "Thanks, that's all."}
    yield {"type": "hangup"}


if __name__ == "__main__":
    compliant_call_flow(simulate_call())
