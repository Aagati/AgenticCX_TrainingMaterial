"""
PM · H1 — Insurance Voice Agent with Claim-Status Tool Call (STARTER)
"""

import json
import time
import random
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("claims_data.json") as f:
    CLAIMS = json.load(f)

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
ENDPOINT_THRESHOLD_MS = 400

GET_CLAIM_STATUS_TOOL = {
    "name": "get_claim_status",
    "description": "Look up the status, filed date, and next step for a claim by id.",
    "input_schema": {
        "type": "object",
        "properties": {"claim_id": {"type": "string"}},
        "required": ["claim_id"],
    },
}


def get_claim_status(claim_id: str) -> dict:
    for c in CLAIMS:
        if c["claim_id"] == claim_id:
            return c
    return {"error": "claim not found"}


def fake_stt(user_utterance: str) -> str:
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return user_utterance


def fake_tts(text: str) -> bytes:
    time.sleep(random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000)
    return text.encode()


def is_turn_complete(silence_ms: int) -> bool:
    return silence_ms >= ENDPOINT_THRESHOLD_MS


SYSTEM_PROMPT = """You are an insurance phone support agent. Reply in
short, natural, spoken-style sentences suitable for text-to-speech — no
markdown, no bullet points. Use get_claim_status when the caller asks
about a specific claim."""


def run_llm_turn(transcript: str):
    """
    TODO 1: Implement the LLM turn, WITH tool use, and return
    (reply_text, num_llm_calls). This mirrors Day 2's tool-use loop:
      - call the model with tools=[GET_CLAIM_STATUS_TOOL]
      - if it calls the tool, execute get_claim_status(), feed the result
        back, and make a second call for the final reply (num_llm_calls=2)
      - if no tool call, just return the text reply (num_llm_calls=1)
    """
    raise NotImplementedError


def run_turn(transcript_so_far: str, silence_ms: int = 500):
    """
    TODO 2: Full instrumented turn:
      1. Check is_turn_complete(silence_ms) — if False, print that the
         agent is still waiting and return None (no turn happens yet).
      2. fake_stt() the transcript.
      3. run_llm_turn() — time this stage.
      4. fake_tts() the reply.
      5. Print a latency breakdown INCLUDING how many LLM calls were made
         (tool-call turns should show roughly double the LLM time).
      Return the reply text.
    """
    raise NotImplementedError


class VoiceAgent:
    """
    TODO 3: Wrap AM·H3's call state machine around run_turn(). Implement:
      - self.state starting at "RINGING"
      - handle_event(event) with the same transitions as AM·H3, except
        "speech" events should call run_turn(event["text"]) instead of a
        bare LLM call.
    """
    def __init__(self):
        self.state = "RINGING"

    def handle_event(self, event: dict):
        raise NotImplementedError


def simulate_call():
    yield {"type": "ring"}
    yield {"type": "answer"}
    yield {"type": "speech", "text": "Hi, can you check the status of claim CLM-3391?"}
    yield {"type": "speech", "text": "Great, thank you!"}
    yield {"type": "hangup"}


if __name__ == "__main__":
    agent = VoiceAgent()
    print(f"[{agent.state}]")
    for event in simulate_call():
        agent.handle_event(event)
        print(f"[{agent.state}]  (event: {event['type']})\n")
