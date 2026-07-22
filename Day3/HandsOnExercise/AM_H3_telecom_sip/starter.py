"""
AM · H3 — Telecom SIP Call State Machine (STARTER)
"""

from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

STATES = ["RINGING", "ANSWERED", "IN_PROGRESS", "ENDED"]


def simulate_incoming_call():
    """Provided — yields a sequence of call events, like a SIP provider would."""
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


def handle_event(state: str, event: dict):
    """
    TODO: Implement the state machine transitions.
      - state RINGING + event "ring" -> stay RINGING, action: None
      - state RINGING + event "answer" -> ANSWERED, action: print a greeting
      - state ANSWERED + event "speech" -> IN_PROGRESS, action: call_llm() and print reply
      - state IN_PROGRESS + event "speech" -> stay IN_PROGRESS, action: call_llm() and print reply
      - state IN_PROGRESS (or ANSWERED) + event "dtmf" with digit "0" ->
        stay in current state, action: print "Transferring to a human agent."
        (don't call the LLM for this)
      - any state + event "hangup" -> ENDED, action: print "Call ended."
    Return the new state.
    """
    raise NotImplementedError


if __name__ == "__main__":
    state = "RINGING"
    print(f"[{state}]")
    for event in simulate_incoming_call():
        state = handle_event(state, event)
        print(f"[{state}]  (event: {event['type']})")
