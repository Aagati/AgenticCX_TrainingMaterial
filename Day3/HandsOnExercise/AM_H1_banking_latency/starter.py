"""
AM · H1 — Banking Voice Loop + Latency Measurement (STARTER)

STT and TTS are SIMULATED (see README) — the LLM call is real and uses
Claude's streaming API, so "LLM ms" genuinely measures time-to-first-token
rather than full completion time.
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
    """
    TODO 1: Simulate STT latency by sleeping for a random duration in
    STT_LATENCY_RANGE_MS (convert ms -> seconds), then just return
    user_utterance unchanged (pretend it was "transcribed" perfectly —
    today's lab is about latency, not accuracy).
    """
    raise NotImplementedError


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


def run_turn(user_utterance: str):
    """
    TODO 4: Time each stage with time.perf_counter():
      - STT: time fake_stt()
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
    for u in utterances:
        print(f"\n--- Turn: \"{u}\" ---")
        run_turn(u)
