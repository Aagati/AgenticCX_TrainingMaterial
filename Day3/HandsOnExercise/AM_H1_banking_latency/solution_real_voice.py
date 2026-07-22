"""
AM · H1 — Banking Voice Loop + Latency Measurement (REAL VOICE VARIANT)

solution.py's fake_stt()/fake_tts() are timing-shaped stand-ins (documented
in the README as a deliberate simplification — no mics/API keys for every
student in the training room). This file swaps them for real calls:
Deepgram Nova-3 for STT, ElevenLabs Flash v2.5 for TTS. The LLM call is
unchanged from solution.py (still real, still streamed) — this file only
replaces the two fakes, so you can diff it against solution.py and see
exactly what a "drop-in replacement" for real SDK calls looks like.

Setup:
    pip install deepgram-sdk elevenlabs
    Set DEEPGRAM_API_KEY and ELEVENLABS_API_KEY in .env (placeholders
    already added at the repo root).

Audio input: Deepgram needs actual audio, not text, so this variant reads
short pre-recorded .wav files instead of a hardcoded utterance list. Put up
to 3 short (<10s) mono WAV files in a `sample_audio/` folder next to this
script — e.g. record them with Windows Voice Recorder, or any text-to-speech
tool you already have — and name them turn_1.wav, turn_2.wav, turn_3.wav.
If the folder is empty, the script tells you what to do and exits cleanly
instead of crashing.
"""

import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic
from deepgram import DeepgramClient
from elevenlabs import ElevenLabs

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for var in ("DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY"):
    if not os.environ.get(var):
        raise RuntimeError(
            f"{var} not set. Add it to .env at the repo root, then "
            f"re-run (`pip install deepgram-sdk elevenlabs` if needed)."
        )

client = Anthropic()
MODEL = "claude-sonnet-5"
BUDGET_MS = 700

deepgram = DeepgramClient(os.environ["DEEPGRAM_API_KEY"])
elevenlabs = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

AUDIO_DIR = Path(__file__).parent / "sample_audio"


def real_stt(audio_path: Path) -> tuple[str, float]:
    """Real Deepgram Nova-3 prerecorded transcription. Returns (transcript, ms)."""
    t0 = time.perf_counter()
    with open(audio_path, "rb") as f:
        response = deepgram.listen.v1.media.transcribe_file(
            request=f.read(), model="nova-3", smart_format=True,
        )
    ms = (time.perf_counter() - t0) * 1000
    transcript = response.results.channels[0].alternatives[0].transcript
    return transcript, ms


def call_llm_streaming(transcript: str):
    """Unchanged from solution.py — the one part that was never simulated."""
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


def real_tts(text: str, out_path: Path) -> float:
    """Real ElevenLabs Flash v2.5 streaming TTS. Returns time-to-first-byte in ms."""
    t0 = time.perf_counter()
    first_byte_time = None
    audio_chunks = []

    stream = elevenlabs.text_to_speech.stream(
        text=text,
        voice_id="21m00Tcm4TlvDq8ikWAM",  # ElevenLabs' default "Rachel" demo voice
        model_id="eleven_flash_v2_5",
    )
    for chunk in stream:
        if first_byte_time is None:
            first_byte_time = time.perf_counter()
        audio_chunks.append(chunk)

    with open(out_path, "wb") as f:
        f.write(b"".join(audio_chunks))

    ttfb = (first_byte_time - t0) if first_byte_time else (time.perf_counter() - t0)
    return ttfb * 1000


def run_turn(audio_path: Path, turn_index: int):
    transcript, stt_ms = real_stt(audio_path)
    reply, ttft, full_completion = call_llm_streaming(transcript)
    llm_ttft_ms = ttft * 1000
    llm_full_ms = full_completion * 1000

    out_path = AUDIO_DIR / f"reply_{turn_index}.mp3"
    tts_ms = real_tts(reply, out_path)

    time_to_first_audio_ms = stt_ms + llm_ttft_ms + tts_ms

    print(f"Transcript (real Deepgram): {transcript}")
    print(f"Reply: {reply}")
    print(f"STT: {stt_ms:.0f}ms | LLM time-to-first-token: {llm_ttft_ms:.0f}ms "
          f"(full completion: {llm_full_ms:.0f}ms) | TTS first-byte: {tts_ms:.0f}ms")
    print(f"TIME TO FIRST AUDIO: {time_to_first_audio_ms:.0f}ms", end="  ")
    print("[WITHIN BUDGET]" if time_to_first_audio_ms <= BUDGET_MS else "[OVER BUDGET]")
    print(f"Reply audio saved to: {out_path}")


if __name__ == "__main__":
    wav_files = sorted(AUDIO_DIR.glob("turn_*.wav")) if AUDIO_DIR.exists() else []
    if not wav_files:
        print(f"No sample audio found in {AUDIO_DIR}.")
        print("Add up to 3 short (<10s) mono WAV files named turn_1.wav, "
              "turn_2.wav, turn_3.wav (e.g. record with Windows Voice "
              "Recorder) and re-run.")
    else:
        for i, wav_path in enumerate(wav_files, start=1):
            print(f"\n--- Turn {i}: {wav_path.name} ---")
            run_turn(wav_path, i)

# Expected: same latency-budget shape as solution.py, but STT/TTS numbers
# now reflect real network calls instead of a random.uniform() sleep — on a
# real connection they'll usually run a bit higher and less predictable than
# the simulated range, which is itself a useful lesson about build-vs-buy
# latency assumptions (Day3 Pre-lunch concept 6).
