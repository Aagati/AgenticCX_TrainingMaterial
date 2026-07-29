"""
PM · H1 — Insurance Voice Agent with Claim-Status Tool Call (STARTER)

STT tries a REAL Deepgram Nova-3 call first (your TODO 1 below) and falls
back to the simulated fake_stt() if DEEPGRAM_API_KEY isn't set, the account
can't reach nova-3, or there's no matching WAV in sample_audio/ — same
pattern as AM·H1. TTS stays simulated either way.
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

# --- Deepgram setup (given — this is plumbing, not today's exercise) ---
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
    """
    TODO 1: Wire the real Deepgram call. Open audio_path in binary mode and
    call deepgram.listen.v1.media.transcribe_file(request=<bytes>,
    model=STT_MODEL, smart_format=True). The response shape is
    response.results.channels[0].alternatives[0].transcript — return that
    string.
    """
    raise NotImplementedError


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
    """Given — the simulated fallback used when real Deepgram isn't
    available for this turn."""
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return user_utterance


def stt(user_utterance: str, audio_path: Path | None) -> str:
    """Given — tries real_stt() against audio_path when Deepgram is
    configured and the file exists; falls back to fake_stt() otherwise
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
    """
    TODO 2: Implement the LLM turn, WITH tool use, and return
    (reply_text, num_llm_calls). This mirrors Day 2's tool-use loop:
      - call the model with tools=[GET_CLAIM_STATUS_TOOL]
      - if it calls the tool, execute get_claim_status(), feed the result
        back, and make a second call for the final reply (num_llm_calls=2)
      - if no tool call, just return the text reply (num_llm_calls=1)
    """
    raise NotImplementedError


def run_turn(transcript_so_far: str, audio_path: Path | None = None, silence_ms: int = 500):
    """
    TODO 3: Full instrumented turn:
      1. Check is_turn_complete(silence_ms) — if False, print that the
         agent is still waiting and return None (no turn happens yet).
      2. stt(transcript_so_far, audio_path) the transcript — NOT fake_stt()
         directly, so a turn with a matching WAV file goes through real
         Deepgram.
      3. run_llm_turn() — time this stage.
      4. fake_tts() the reply.
      5. Print a latency breakdown INCLUDING how many LLM calls were made
         (tool-call turns should show roughly double the LLM time).
      Return the reply text.
    """
    raise NotImplementedError


class VoiceAgent:
    """
    TODO 4: Wrap AM·H3's call state machine around run_turn(). Implement:
      - self.state starting at "RINGING"
      - self.turn_index starting at 0 (increment it on each "speech" event
        so you can pair the turn with sample_audio/turn_<n>.wav)
      - handle_event(event) with the same transitions as AM·H3, except
        "speech" events should bump self.turn_index, build
        wav_path = AUDIO_DIR / f"turn_{self.turn_index}.wav", and call
        run_turn(event["text"], wav_path if wav_path.exists() else None)
        instead of a bare LLM call.
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

# To exercise the REAL Deepgram path instead of the simulated one: set
# DEEPGRAM_API_KEY in .env, `pip install deepgram-sdk`, and drop up to 2
# short (<10s) mono WAV files into a sample_audio/ folder next to this
# script, named turn_1.wav (claim question), turn_2.wav ("Great, thank
# you!"). No WAVs / no key -> falls back to the simulation, no code changes
# needed either way.
