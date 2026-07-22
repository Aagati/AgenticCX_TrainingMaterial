"""
AM · H1 — Banking Voice Loop + Latency Measurement (REFERENCE SOLUTION)

STT and TTS are SIMULATED (see README) — the LLM call is real, and uses
Claude's streaming API so "LLM ms" genuinely measures time-to-first-token,
not full completion time. This matters: a voice pipeline can start TTS the
moment the first token/sentence arrives — waiting for the whole response
before speaking would add real, avoidable latency.
"""

import time
import random
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
BUDGET_MS = 700


def fake_stt(user_utterance: str) -> str:
    delay_s = random.uniform(*STT_LATENCY_RANGE_MS) / 1000
    time.sleep(delay_s)
    return user_utterance


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


def run_turn(user_utterance: str):
    t0 = time.perf_counter()
    transcript = fake_stt(user_utterance)
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

    print(f"Transcript: {transcript}")
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
    for u in utterances:
        print(f"\n--- Turn: \"{u}\" ---")
        run_turn(u)

# Expected: STT and TTS stay small and predictable. LLM time-to-first-token
# is usually the largest, most variable chunk of TIME TO FIRST AUDIO — and
# it's meaningfully smaller than "full completion," which is the whole
# point: a pipeline that waits for full completion before starting TTS is
# leaving real latency on the table.
