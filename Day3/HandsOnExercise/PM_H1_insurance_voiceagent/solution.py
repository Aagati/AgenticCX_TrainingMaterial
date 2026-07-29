"""
PM · H1 — Insurance Voice Agent with Claim-Status Tool Call (REFERENCE SOLUTION)

STT tries a REAL Deepgram Nova-3 call first (see resolve_stt_model() /
real_stt() below) and transparently falls back to the simulated fake_stt()
if DEEPGRAM_API_KEY isn't set, the account can't reach nova-3, or there's no
matching WAV file in sample_audio/ for a given turn — same pattern as
AM·H1. TTS stays simulated either way.
"""

import json
import os
import time
import random
from pathlib import Path

from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open(Path(__file__).parent / "claims_data.json") as f:
    CLAIMS = json.load(f)

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
ENDPOINT_THRESHOLD_MS = 400

AUDIO_DIR = Path(__file__).parent / "sample_audio"
STT_MODEL_PREFERRED = "nova-3"
STT_MODEL_FALLBACK = "nova-2"  # one tier down — cheaper per-minute, still batch-capable

deepgram = None
STT_MODEL = None

if os.environ.get("DEEPGRAM_API_KEY"):
    try:
        from deepgram import DeepgramClient
        from deepgram.core.api_error import ApiError as DeepgramApiError

        deepgram = DeepgramClient(api_key=os.environ["DEEPGRAM_API_KEY"])

        def resolve_stt_model() -> str:
            """Preflight the key against Deepgram's /v1/models endpoint
            (management API — free, no transcription credits burned) and
            confirm the account's batch catalog has a nova-3 variant. "nova-3"
            never appears literally in the catalog — it's a version alias
            that resolves server-side to canonical names like
            "nova-3-general" — so the check matches on that prefix."""
            try:
                models = deepgram.manage.v1.models.list(include_outdated=False)
                batch_canonical = {
                    m.canonical_name for m in (models.stt or [])
                    if m.batch and m.canonical_name
                }
                if any(n.startswith(STT_MODEL_PREFERRED) for n in batch_canonical):
                    return STT_MODEL_PREFERRED
                print(f"Deepgram key can't reach '{STT_MODEL_PREFERRED}' "
                      f"(no matching model in this account's batch catalog) — "
                      f"using '{STT_MODEL_FALLBACK}'.")
            except DeepgramApiError as exc:
                print(f"Deepgram model check failed ({exc}) — using '{STT_MODEL_FALLBACK}'.")
            return STT_MODEL_FALLBACK

        STT_MODEL = resolve_stt_model()
    except Exception as exc:
        print(f"Deepgram setup failed ({exc}) — real STT disabled, using simulated STT.")
        deepgram = None


def real_stt(audio_path: Path) -> str:
    """Real Deepgram prerecorded transcription using STT_MODEL."""
    with open(audio_path, "rb") as f:
        response = deepgram.listen.v1.media.transcribe_file(
            request=f.read(), model=STT_MODEL, smart_format=True,
        )
    return response.results.channels[0].alternatives[0].transcript


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


def stt(user_utterance: str, audio_path: Path | None) -> str:
    """Tries real Deepgram STT against audio_path when it's configured and
    the file exists; falls back to the simulated fake_stt() otherwise
    (missing key, model unavailable, no WAV for this turn, or the call
    itself fails at runtime)."""
    if deepgram is not None and audio_path is not None and audio_path.exists():
        try:
            return real_stt(audio_path)
        except Exception as exc:
            print(f"Deepgram STT call failed ({exc}) — falling back to simulated STT.")
    return fake_stt(user_utterance)


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


def run_turn(transcript_so_far: str, audio_path: Path | None = None, silence_ms: int = 500):
    if not is_turn_complete(silence_ms):
        print("  ... (still waiting, silence below endpointing threshold)")
        return None

    t0 = time.perf_counter()
    transcript = stt(transcript_so_far, audio_path)
    t1 = time.perf_counter()

    reply, num_llm_calls = run_llm_turn(transcript)
    t2 = time.perf_counter()

    fake_tts(reply)
    t3 = time.perf_counter()

    stt_ms, llm_ms, tts_ms, total_ms = (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000, (t3 - t0) * 1000
    source = f"real Deepgram, model={STT_MODEL}" if (deepgram and audio_path and audio_path.exists()) else "simulated"
    print(f"  Caller ({source}): \"{transcript}\"")
    print(f"  Agent: \"{reply}\"")
    print(f"  [STT {stt_ms:.0f}ms | LLM {llm_ms:.0f}ms ({num_llm_calls} call"
          f"{'s' if num_llm_calls > 1 else ''}) | TTS {tts_ms:.0f}ms | TOTAL {total_ms:.0f}ms]")
    return reply


class VoiceAgent:
    def __init__(self):
        self.state = "RINGING"
        self.turn_index = 0

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
            self.turn_index += 1
            wav_path = AUDIO_DIR / f"turn_{self.turn_index}.wav"
            run_turn(event["text"], wav_path if wav_path.exists() else None)
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
#
# To exercise the REAL Deepgram path instead of the simulated one: set
# DEEPGRAM_API_KEY in .env, `pip install deepgram-sdk`, and drop up to 2
# short (<10s) mono WAV files into a sample_audio/ folder next to this
# script, named turn_1.wav (claim question), turn_2.wav ("Great, thank
# you!"). No WAVs / no key -> falls back to the simulation, no code changes
# needed either way.
