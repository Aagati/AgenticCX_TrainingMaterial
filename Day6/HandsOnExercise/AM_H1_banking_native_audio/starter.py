"""
AM · H1 — Banking: Pipeline vs. Native Audio (STARTER)

Native path tries a REAL Gemini Live API call first (your TODO 3 below) and
falls back to a simulated single-hop draw if GEMINI_API_KEY isn't set, the
SDK isn't installed, or the call fails at runtime — so this lab runs for
every student, key or no key. The modular path's LLM stage is a real
streamed Claude call either way (TODO 1).
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
    """Given — simulated STT latency draw, same band as Day 3's AM_H1."""
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return user_utterance


def call_llm_streaming(transcript: str) -> tuple[str, float]:
    """
    TODO 1: A REAL streamed Claude call using client.messages.stream() as a
    context manager (model=CLAUDE_MODEL, max_tokens=60, system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": transcript}]). Accumulate
    stream.text_stream into the full reply text. Return
    (reply_text, elapsed_seconds) where elapsed_seconds is measured with
    time.perf_counter() around the whole call.
    """
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
    """Given — simulated TTS first-byte draw, same band as Day 3's AM_H1."""
    delay_s = random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000
    time.sleep(delay_s)
    return delay_s


def run_modular_turn(user_utterance: str) -> dict:
    """
    TODO 2: Time each stage with time.perf_counter() — fake_stt(), then
    call_llm_streaming(), then fake_tts() on the reply. Return a dict with
    "reply", "stages" ({"stt_ms","llm_ms","tts_ms"}), "total_ms" (sum of the
    three), and "hops": 3.
    """
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
    """
    TODO 3: Wire the real Gemini Live API call.
      1. Build config = genai_types.LiveConnectConfig(response_modalities=
         ["AUDIO"], system_instruction=SYSTEM_PROMPT).
      2. async with genai_client.aio.live.connect(model=NATIVE_AUDIO_MODEL,
         config=config) as session: send the turn with
         await session.send_client_content(turns={"parts": [{"text":
         user_utterance}]}, turn_complete=True).
      3. `async for message in session.receive():` — message.server_content
         holds .model_turn.parts (each part may have .inline_data.data =
         raw audio bytes, or .text). Record time.perf_counter() the FIRST
         time you see inline_data (time-to-first-audio). Accumulate audio
         bytes and any text parts. Stop once server_content.turn_complete
         is truthy.
      4. Return a dict: "reply" (joined text parts, or a placeholder if
         audio-only), "time_to_first_audio_ms", "total_ms", "audio_bytes"
         (len of accumulated bytes), "hops": 1, "real": True.
    """
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
    """Given — dispatches to the real async Live call when Gemini is
    configured; falls back to a single-hop simulated draw otherwise (no
    key, SDK missing, or the call fails at runtime)."""
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
    """
    TODO 4: Call run_modular_turn() and run_native_turn() for the same
    utterance. Print a breakdown of each (modular's per-stage ms + total;
    native's time-to-first-audio + total + whether it was real or
    simulated), then print the delta between the two totals and which one
    was faster.
    """
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
