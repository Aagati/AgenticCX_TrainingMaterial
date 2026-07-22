"""
AM · H3 — Telecom SIP Call State Machine (REFERENCE SOLUTION)
"""

from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"


def simulate_incoming_call():
    yield {"type": "ring"}
    yield {"type": "answer"}
    yield {"type": "speech", "text": "Hi, I want to check my data usage this month."}
    yield {"type": "speech", "text": "Also, what's my current plan?"}
    yield {"type": "dtmf", "digit": "0"}
    yield {"type": "hangup"}


def call_llm(transcript: str) -> str:
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system=(
            "You are a telecom phone support agent. Reply in short, natural, "
            "spoken-style sentences suitable for text-to-speech. No markdown."
        ),
        messages=[{"role": "user", "content": transcript}],
    )
    return response.content[0].text


def handle_event(state: str, event: dict) -> str:
    etype = event["type"]

    if etype == "hangup":
        print("  -> Call ended.")
        return "ENDED"

    if etype == "ring" and state == "RINGING":
        return "RINGING"

    if etype == "answer" and state == "RINGING":
        print("  -> Greeting: \"Thanks for calling, how can I help you today?\"")
        return "ANSWERED"

    if etype == "dtmf" and event.get("digit") == "0" and state in ("ANSWERED", "IN_PROGRESS"):
        print("  -> Transferring to a human agent.")
        return state

    if etype == "speech" and state in ("ANSWERED", "IN_PROGRESS"):
        reply = call_llm(event["text"])
        print(f"  -> Customer: \"{event['text']}\"")
        print(f"  -> Agent: \"{reply}\"")
        return "IN_PROGRESS"

    print(f"  -> (unhandled event {etype} in state {state})")
    return state


if __name__ == "__main__":
    state = "RINGING"
    print(f"[{state}]")
    for event in simulate_incoming_call():
        state = handle_event(state, event)
        print(f"[{state}]  (event: {event['type']})")

# Expected transitions:
# RINGING -(ring)-> RINGING -(answer)-> ANSWERED -(speech)-> IN_PROGRESS
# -(speech)-> IN_PROGRESS -(dtmf "0")-> IN_PROGRESS (transfer message,
# no LLM call) -(hangup)-> ENDED
