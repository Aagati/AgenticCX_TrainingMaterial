"""
AM · H1 — Banking: Pipeline vs. Native Audio (REFERENCE SOLUTION)

The same customer turn, run two ways:
  1. MODULAR — fake_stt -> real streamed Claude call -> fake_tts. Three
     separate hops, three separate latency budgets to sum. This is the
     Day 3 shape (AM_H1_banking_latency), unchanged.
  2. NATIVE  — one Gemini Live API session on a native-audio-dialog model,
     text turn in / audio turn out, in a SINGLE hop. There is no discrete
     STT stage, LLM stage, or TTS stage to time separately — the model
     produces speech directly from the conversation, which is the whole
     point of "pipeline to native audio."

The native path is REAL if GEMINI_API_KEY (or GOOGLE_API_KEY) is set —
genai.Client() picks either up from the environment automatically — and
falls back to a single-hop simulated latency draw otherwise, so the lab
runs for every student, key or no key. Same "real-if-key" contract Day 3
uses for Deepgram.
"""

import asyncio
import os
import random
import sys
import time

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# Windows consoles default to cp1252 and will crash on the model's em-dashes
# and curly quotes. Force UTF-8 so the lab doesn't die on a print().
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

anthropic_client = Anthropic()
CLAUDE_MODEL = "claude-sonnet-5"

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
NATIVE_AUDIO_SIM_RANGE_MS = (250, 400)  # single-hop draw used only when no key

# Current native-audio-dialog model id as of this writing (see
# ai.google.dev/gemini-api/docs/models) — native-audio model ids change
# often between preview releases, check for a newer one before class.
NATIVE_AUDIO_MODEL = "gemini-live-2.5-flash-native-audio"

SYSTEM_PROMPT = (
    "You are a banking phone support agent. Reply in short, natural, "
    "spoken-style sentences — this gets read aloud, not displayed as "
    "text. No bullet points, no markdown."
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _vertex_client import get_genai_client, save_pcm_wav

AUDIO_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_audio_out")

genai_client, genai_types = get_genai_client(location="us-central1")
if genai_client is None:
    print("No working Gemini credentials — native path will use simulation.")
    genai_client = None


def fake_stt(user_utterance: str) -> str:
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return user_utterance


def call_llm_streaming(transcript: str) -> tuple[str, float]:
    """Real streamed Claude call. Returns (reply_text, elapsed_seconds)."""
    t0 = time.perf_counter()
    chunks = []
    with anthropic_client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=60,
        # claude-sonnet-5 defaults to extended thinking on; with a budget
        # this small the model can burn the ENTIRE max_tokens on a thinking
        # block and hit stop_reason="max_tokens" with zero text emitted.
        # Disabling it keeps this lab's tiny budget going to the spoken
        # reply, which is the only thing this lab is timing.
        thinking={"type": "disabled"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    return "".join(chunks), time.perf_counter() - t0


def fake_tts(text: str) -> float:
    delay_s = random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000
    time.sleep(delay_s)
    return delay_s


def run_modular_turn(user_utterance: str) -> dict:
    t0 = time.perf_counter()
    transcript = fake_stt(user_utterance)
    stt_ms = (time.perf_counter() - t0) * 1000

    reply, llm_s = call_llm_streaming(transcript)
    llm_ms = llm_s * 1000

    tts_s = fake_tts(reply)
    tts_ms = tts_s * 1000

    return {
        "reply": reply,
        "stages": {"stt_ms": stt_ms, "llm_ms": llm_ms, "tts_ms": tts_ms},
        "total_ms": stt_ms + llm_ms + tts_ms,
        "hops": 3,
    }


async def _run_native_turn_async(user_utterance: str) -> dict:
    config = genai_types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_PROMPT,
    )
    t0 = time.perf_counter()
    first_audio_time = None
    audio_bytes = bytearray()
    reply_text_parts = []

    async with genai_client.aio.live.connect(model=NATIVE_AUDIO_MODEL, config=config) as session:
        await session.send_client_content(
            turns={"parts": [{"text": user_utterance}]}, turn_complete=True,
        )
        async for message in session.receive():
            sc = message.server_content
            if sc is None:
                continue
            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        if first_audio_time is None:
                            first_audio_time = time.perf_counter()
                        audio_bytes.extend(part.inline_data.data)
                    if part.text:
                        reply_text_parts.append(part.text)
            if sc.turn_complete:
                break

    total_ms = (time.perf_counter() - t0) * 1000
    ttfa_ms = ((first_audio_time - t0) * 1000) if first_audio_time else total_ms
    audio_path = None
    if audio_bytes:
        fname = f"native_{int(t0 * 1000)}.wav"
        audio_path = save_pcm_wav(bytes(audio_bytes), os.path.join(AUDIO_OUT_DIR, fname))
    return {
        "reply": "".join(reply_text_parts) or "(audio-only reply — model didn't return a text part)",
        "time_to_first_audio_ms": ttfa_ms,
        "total_ms": total_ms,
        "audio_bytes": len(audio_bytes),
        "audio_path": audio_path,
        "hops": 1,
        "real": True,
    }


def run_native_turn(user_utterance: str) -> dict:
    """Real Gemini Live call when configured; single-hop simulated draw
    otherwise (no key, SDK missing, or the call fails at runtime)."""
    if genai_client is not None:
        try:
            return asyncio.run(_run_native_turn_async(user_utterance))
        except Exception as exc:
            print(f"Gemini Live call failed ({exc}) — falling back to simulated native path.")

    delay_s = random.uniform(*NATIVE_AUDIO_SIM_RANGE_MS) / 1000
    time.sleep(delay_s)
    return {
        "reply": "(simulated native-audio reply — no GEMINI_API_KEY set)",
        "time_to_first_audio_ms": delay_s * 1000,
        "total_ms": delay_s * 1000,
        "audio_bytes": 0,
        "audio_path": None,
        "hops": 1,
        "real": False,
    }


def compare_turn(user_utterance: str):
    print(f'\n--- "{user_utterance}" ---')

    modular = run_modular_turn(user_utterance)
    native = run_native_turn(user_utterance)

    print(
        f"MODULAR (3 hops): stt={modular['stages']['stt_ms']:.0f}ms "
        f"llm={modular['stages']['llm_ms']:.0f}ms "
        f"tts={modular['stages']['tts_ms']:.0f}ms "
        f"-> total {modular['total_ms']:.0f}ms"
    )
    print(f"  reply: {modular['reply']}")

    source = "real Gemini Live" if native.get("real") else "simulated (no GEMINI_API_KEY)"
    print(
        f"NATIVE  (1 hop, {source}): time-to-first-audio="
        f"{native['time_to_first_audio_ms']:.0f}ms, total={native['total_ms']:.0f}ms, "
        f"audio_bytes={native['audio_bytes']}"
    )
    print(f"  reply: {native['reply']}")
    if native.get("audio_path"):
        print(f"  audio saved: {native['audio_path']}")

    delta = modular["total_ms"] - native["total_ms"]
    print(f"DELTA: native is {abs(delta):.0f}ms {'faster' if delta > 0 else 'slower'} than modular")


if __name__ == "__main__":
    utterances = [
        "What's my account balance?",
        "Can you tell me if my paycheck deposited yet?",
        "I need to report my card as lost.",
    ]
    for u in utterances:
        compare_turn(u)

# Expected (simulated native path, no key): native total (~250-400ms, one
# draw) beats modular total (~120-220 + real Claude latency + 60-100ms,
# three draws plus a real network call) on every turn, and the gap WIDENS
# whenever the modular LLM stage runs long — because modular pays for three
# hops' worth of variance while native only pays for one. With a real
# GEMINI_API_KEY, expect the same qualitative shape but native's own
# variance now comes from one real network round trip instead of a fixed
# random.uniform band.
