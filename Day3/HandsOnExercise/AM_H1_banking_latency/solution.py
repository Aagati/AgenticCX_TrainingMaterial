"""
AM · H1 — Banking Voice Loop + Latency Measurement (REFERENCE SOLUTION)

STT tries a REAL Deepgram Nova-3 call first (see resolve_stt_model() /
real_stt() below) and transparently falls back to the simulated fake_stt()
if DEEPGRAM_API_KEY isn't set, the account can't reach nova-3, or there's no
matching WAV file in sample_audio/ for a given turn — so this lab still runs
for every student in the room, key or no key. TTS stays simulated either
way (see README) — the LLM call is real and uses Claude's streaming API, so
"LLM ms" genuinely measures time-to-first-token, not full completion time.
This matters: a voice pipeline can start TTS the moment the first
token/sentence arrives — waiting for the whole response before speaking
would add real, avoidable latency.
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


def fake_stt(user_utterance: str) -> str:
    delay_s = random.uniform(*STT_LATENCY_RANGE_MS) / 1000
    time.sleep(delay_s)
    return user_utterance


def stt(user_utterance: str, audio_path: Path | None) -> str:
    """Try real Deepgram STT against audio_path when it's configured and the
    file exists; fall back to the simulated fake_stt() otherwise (missing
    key, model unavailable, no WAV for this turn, or the call itself fails
    at runtime)."""
    if deepgram is not None and audio_path is not None and audio_path.exists():
        try:
            return real_stt(audio_path)
        except Exception as exc:
            print(f"Deepgram STT call failed ({exc}) — falling back to simulated STT.")
    return fake_stt(user_utterance)


def call_llm_streaming(transcript: str):
    """Real streaming call. Returns (full_text, time_to_first_token_seconds,
    full_completion_seconds) so the caller can report BOTH — the number that
    actually gates when TTS can start (first token) and the number that
    tells you how long the whole reply took (full completion)."""
    t_start = time.perf_counter()
    first_token_time = None
    chunks = []

    with client.messages.stream(
        model=MODEL,
        max_tokens=60,
        system=(
            "You are a banking phone support agent. Reply in short, natural, "
            "spoken-style sentences — this response will be read aloud by a "
            "voice synthesizer, not displayed as text. No bullet points, no markdown."
        ),
        messages=[{"role": "user", "content": transcript}],
    ) as stream:
        for text in stream.text_stream:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            chunks.append(text)

    t_end = time.perf_counter()
    full_text = "".join(chunks)
    ttft = (first_token_time - t_start) if first_token_time else (t_end - t_start)
    full_completion = t_end - t_start
    return full_text, ttft, full_completion


def fake_tts(text: str) -> bytes:
    delay_s = random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000
    time.sleep(delay_s)
    return text.encode()


def run_turn(user_utterance: str, audio_path: Path | None = None):
    t0 = time.perf_counter()
    transcript = stt(user_utterance, audio_path)
    t1 = time.perf_counter()
    stt_ms = (t1 - t0) * 1000

    reply, ttft, full_completion = call_llm_streaming(transcript)
    llm_ttft_ms = ttft * 1000
    llm_full_ms = full_completion * 1000

    t2 = time.perf_counter()
    _audio = fake_tts(reply)
    t3 = time.perf_counter()
    tts_ms = (t3 - t2) * 1000

    time_to_first_audio_ms = stt_ms + llm_ttft_ms + tts_ms

    source = f"real Deepgram, model={STT_MODEL}" if (deepgram and audio_path and audio_path.exists()) else "simulated"
    print(f"Transcript ({source}): {transcript}")
    print(f"Reply: {reply}")
    print(f"STT: {stt_ms:.0f}ms | LLM time-to-first-token: {llm_ttft_ms:.0f}ms "
          f"(full completion: {llm_full_ms:.0f}ms) | TTS first-byte: {tts_ms:.0f}ms")
    print(f"TIME TO FIRST AUDIO: {time_to_first_audio_ms:.0f}ms", end="  ")
    print("[WITHIN BUDGET]" if time_to_first_audio_ms <= BUDGET_MS else "[OVER BUDGET]")


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

# Expected: STT and TTS stay small and predictable. LLM time-to-first-token
# is usually the largest, most variable chunk of TIME TO FIRST AUDIO — and
# it's meaningfully smaller than "full completion," which is the whole
# point: a pipeline that waits for full completion before starting TTS is
# leaving real latency on the table.
#
# To exercise the REAL Deepgram path instead of the simulated one: set
# DEEPGRAM_API_KEY in .env, `pip install deepgram-sdk`, and drop up to 3
# short (<10s) mono WAV files into a sample_audio/ folder next to this
# script, named turn_1.wav, turn_2.wav, turn_3.wav (e.g. record with Windows
# Voice Recorder). No WAVs / no key -> falls back to the simulation above,
# no code changes needed either way.
