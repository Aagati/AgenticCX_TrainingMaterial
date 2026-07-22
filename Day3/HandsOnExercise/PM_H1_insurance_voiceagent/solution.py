"""
PM · H1 — Insurance Voice Agent with Claim-Status Tool Call (REFERENCE SOLUTION)
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
    messages = [{"role": "user", "content": transcript}]
    response = client.messages.create(
        model=MODEL, max_tokens=80, system=SYSTEM_PROMPT,
        tools=[GET_CLAIM_STATUS_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        text = next(b.text for b in response.content if b.type == "text")
        return text, 1

    result = get_claim_status(**tool_use.input)
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=80, system=SYSTEM_PROMPT,
        tools=[GET_CLAIM_STATUS_TOOL], messages=messages,
    )
    text = next(b.text for b in followup.content if b.type == "text")
    return text, 2


def run_turn(transcript_so_far: str, silence_ms: int = 500):
    if not is_turn_complete(silence_ms):
        print("  ... (still waiting, silence below endpointing threshold)")
        return None

    t0 = time.perf_counter()
    transcript = fake_stt(transcript_so_far)
    t1 = time.perf_counter()

    reply, num_llm_calls = run_llm_turn(transcript)
    t2 = time.perf_counter()

    fake_tts(reply)
    t3 = time.perf_counter()

    stt_ms, llm_ms, tts_ms, total_ms = (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000, (t3 - t0) * 1000
    print(f"  Caller: \"{transcript}\"")
    print(f"  Agent: \"{reply}\"")
    print(f"  [STT {stt_ms:.0f}ms | LLM {llm_ms:.0f}ms ({num_llm_calls} call"
          f"{'s' if num_llm_calls > 1 else ''}) | TTS {tts_ms:.0f}ms | TOTAL {total_ms:.0f}ms]")
    return reply


class VoiceAgent:
    def __init__(self):
        self.state = "RINGING"

    def handle_event(self, event: dict):
        etype = event["type"]
        if etype == "hangup":
            print("  -> Call ended.")
            self.state = "ENDED"
        elif etype == "ring" and self.state == "RINGING":
            pass
        elif etype == "answer" and self.state == "RINGING":
            print("  -> Greeting: \"Thanks for calling, how can I help you today?\"")
            self.state = "ANSWERED"
        elif etype == "speech" and self.state in ("ANSWERED", "IN_PROGRESS"):
            run_turn(event["text"])
            self.state = "IN_PROGRESS"
        return self.state


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

# Expected: the first speech turn (claim lookup) shows 2 LLM calls and
# noticeably higher LLM ms than the second turn ("Great, thank you!"),
# which needs no tool and stays at 1 call.
