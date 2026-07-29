"""
AM · H1 — Banking Voice Loop + Latency Measurement (STARTER)

STT tries a REAL Deepgram Nova-3 call first (your TODO 1 below) and falls
back to the simulated fake_stt() if DEEPGRAM_API_KEY isn't set, the account
can't reach nova-3, or there's no matching WAV in sample_audio/ — so this
lab runs for every student, key or no key. TTS stays simulated either way
(see README) — the LLM call is real and uses Claude's streaming API, so
"LLM ms" genuinely measures time-to-first-token rather than full completion
time.
"""

import os
import time
import random
from pathlib import Path

from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
BUDGET_MS = 700

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


def fake_stt(user_utterance: str) -> str:
    """Given — the simulated fallback used when real Deepgram isn't
    available for this turn."""
    delay_s = random.uniform(*STT_LATENCY_RANGE_MS) / 1000
    time.sleep(delay_s)
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


def call_llm_streaming(transcript: str):
    """
    TODO 2: A REAL streaming call to Claude using client.messages.stream()
    as a context manager. System prompt: a banking phone agent, short
    spoken-style sentences, no markdown. As you iterate
    `for text in stream.text_stream:`, record time.perf_counter() the FIRST
    time you receive a chunk (that's time-to-first-token) and accumulate
    all chunks into the full reply text.
    Return (full_text, time_to_first_token_seconds, full_completion_seconds).
    """
    raise NotImplementedError


def fake_tts(text: str) -> bytes:
    """
    TODO 3: Simulate TTS time-to-first-audio-byte by sleeping for a random
    duration in TTS_FIRST_BYTE_RANGE_MS, then return a placeholder bytes
    object (e.g. text.encode()) standing in for synthesized audio.
    """
    raise NotImplementedError


def run_turn(user_utterance: str, audio_path: Path | None = None):
    """
    TODO 4: Time each stage with time.perf_counter():
      - STT: time stt(user_utterance, audio_path) — NOT fake_stt() directly,
        so a turn with a matching WAV file goes through real Deepgram
      - LLM: call call_llm_streaming(); use the returned ttft directly
        (it's already measured internally) and also report full_completion
        for comparison
      - TTS: time fake_tts() directly (a fresh perf_counter pair around
        just that call — don't reuse an old timestamp)
    Compute TIME TO FIRST AUDIO = stt_ms + llm_ttft_ms + tts_ms (this is
    the number that determines whether the customer perceives the agent as
    responsive — NOT stt_ms + llm_full_completion_ms + tts_ms).
    Print a breakdown showing STT, LLM time-to-first-token (and full
    completion for comparison), TTS, and whether TIME TO FIRST AUDIO is
    within BUDGET_MS.
    """
    raise NotImplementedError


if __name__ == "__main__":
    utterances = [
        "What's my account balance?",
        "Can you tell me if my paycheck deposited yet?",
        "I need to report my card as lost.",
    ]
    for i, u in enumerate(utterances, start=1):
        print(f"\n--- Turn: \"{u}\" ---")
        wav_path = AUDIO_DIR / f"turn_{i}.wav"
        run_turn(u, wav_path if wav_path.exists() else None)

# To exercise the REAL Deepgram path instead of the simulated one: set
# DEEPGRAM_API_KEY in .env, `pip install deepgram-sdk`, and drop up to 3
# short (<10s) mono WAV files into a sample_audio/ folder next to this
# script, named turn_1.wav, turn_2.wav, turn_3.wav (e.g. record with Windows
# Voice Recorder). No WAVs / no key -> falls back to the simulation, no
# code changes needed either way.
