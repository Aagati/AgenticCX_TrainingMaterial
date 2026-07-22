"""
PM · H3 — Telecom Compliant Call Flow (REFERENCE SOLUTION)
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
    print("Agent: \"Before we continue — you're speaking with an AI assistant, not a human agent.\"")
    call_log.append({"event": "disclosure_given", "timestamp": now_iso()})


def request_recording_consent(call_log: list, caller_response: str):
    print("Agent: \"This call may be recorded for quality purposes. Is that okay with you?\"")
    refused = "no" in caller_response.lower() or "don't" in caller_response.lower()
    granted = not refused
    call_log.append({"event": "recording_consent", "granted": granted, "timestamp": now_iso()})
    if granted:
        print(f"  Caller: \"{caller_response}\"  -> Recording: ON")
    else:
        print(f"  Caller: \"{caller_response}\"  -> Recording: OFF (call continues unrecorded)")


def check_erasure_request(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in ERASURE_KEYWORDS)


def call_llm(transcript: str) -> str:
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system="You are a telecom phone support agent. Reply in short, natural, spoken-style sentences. No markdown.",
        messages=[{"role": "user", "content": transcript}],
    )
    return response.content[0].text


def handle_speech(text: str, call_log: list) -> str:
    if check_erasure_request(text):
        reply = "Understood — I've logged a request to erase your data from this call. Our privacy team will confirm within 30 days."
        print(f"  Caller: \"{text}\"")
        print(f"  Agent: \"{reply}\"")
        call_log.append({"event": "erasure_requested", "timestamp": now_iso(), "text": text})
        return reply

    reply = call_llm(text)
    print(f"  Caller: \"{text}\"")
    print(f"  Agent: \"{reply}\"")
    call_log.append({"event": "turn", "caller": text, "agent": reply, "timestamp": now_iso()})
    return reply


def compliant_call_flow(events):
    call_log = []
    pending_consent_prompt = False

    for event in events:
        etype = event["type"]

        if etype == "answer":
            disclose_ai(call_log)
            pending_consent_prompt = True

        elif etype == "consent_response" and pending_consent_prompt:
            request_recording_consent(call_log, event["text"])
            pending_consent_prompt = False

        elif etype == "speech":
            handle_speech(event["text"], call_log)

        elif etype == "hangup":
            print("Call ended.")
            break

    print("\n=== Full call_log (audit trail) ===")
    print(json.dumps(call_log, indent=2))
    return call_log


def simulate_call():
    yield {"type": "answer"}
    yield {"type": "consent_response", "text": "Sure, that's fine."}
    yield {"type": "speech", "text": "Hi, I want to check my data usage this month."}
    yield {"type": "speech", "text": "Actually, can you delete my data from this call?"}
    yield {"type": "speech", "text": "Thanks, that's all."}
    yield {"type": "hangup"}


if __name__ == "__main__":
    compliant_call_flow(simulate_call())

# Expected call_log: disclosure_given -> recording_consent(granted=True)
# -> turn (data usage question) -> erasure_requested (NOT a normal LLM
# turn) -> turn ("thanks, that's all"). Four distinct event types in the
# audit trail, in order.
