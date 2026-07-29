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

import contextlib
import json
import os
import time
import random
import wave
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

with open(Path(__file__).parent / "account_ledger.json") as f:
    ACCOUNT = json.load(f)

GET_ACCOUNT_INFO_TOOL = {
    "name": "get_account_info",
    "description": "Look up the caller's current balance, card status, and most recent paycheck deposit.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

FREEZE_CARD_TOOL = {
    "name": "freeze_card",
    "description": "Freeze the caller's card immediately — use this when they report it lost or stolen.",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

TOOLS = [GET_ACCOUNT_INFO_TOOL, FREEZE_CARD_TOOL]


def get_account_info() -> dict:
    return {k: v for k, v in ACCOUNT.items() if k != "customer_id"}


def freeze_card() -> dict:
    ACCOUNT["card_status"] = "frozen"
    return {"card_status": ACCOUNT["card_status"], "confirmation": "Card frozen successfully."}


TOOL_FUNCS = {"get_account_info": get_account_info, "freeze_card": freeze_card}

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
BUDGET_MS = 700

AUDIO_DIR = Path(__file__).parent / "sample_audio"
STT_MODEL_PREFERRED = "nova-3"
STT_MODEL_FALLBACK = "nova-2"  # one tier down — cheaper per-minute, still batch-capable
TTS_MODEL = "aura-2-asteria-en"
TTS_ENCODING = "linear16"  # raw PCM — the streaming TTS socket only speaks
TTS_SAMPLE_RATE = "16000"  # linear16/mulaw/alaw, not mp3 (that's REST-only)

deepgram = None
STT_MODEL = None
SpeakV1Text = None

if os.environ.get("DEEPGRAM_API_KEY"):
    try:
        from deepgram import DeepgramClient
        from deepgram.core.api_error import ApiError as DeepgramApiError
        from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

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


SYSTEM_PROMPT = (
    "You are a banking phone support agent. Reply in short, natural, "
    "spoken-style sentences — this response will be read aloud by a voice "
    "synthesizer, not displayed as text. No bullet points, no markdown. "
    "Use get_account_info for balance or deposit questions, and freeze_card "
    "when the caller reports their card lost or stolen."
)


def call_llm_streaming(transcript: str):
    """Real streaming call, with tool use. Returns (full_text,
    time_to_first_token_seconds, full_completion_seconds, num_llm_calls).

    The first streamed call may resolve to a tool_use block instead of text
    (get_account_info / freeze_card) — when it does, we execute the tool and
    make a SECOND streamed call with the result fed back in. Whichever call
    actually produces the spoken reply is the one whose first-token time we
    report: that's the number that gates when TTS can start, same as
    PM·H1's num_llm_calls — tool turns cost roughly double the LLM time,
    and the caller should be able to see that."""
    t_start = time.perf_counter()
    messages = [{"role": "user", "content": transcript}]

    first_token_time = None
    chunks = []
    with client.messages.stream(
        model=MODEL, max_tokens=60, system=SYSTEM_PROMPT,
        tools=TOOLS, messages=messages,
    ) as stream:
        for text in stream.text_stream:
            if first_token_time is None:
                first_token_time = time.perf_counter()
            chunks.append(text)
        final = stream.get_final_message()

    num_llm_calls = 1
    tool_use = next((b for b in final.content if b.type == "tool_use"), None)

    if tool_use is not None:
        result = TOOL_FUNCS[tool_use.name]()
        messages.append({"role": "assistant", "content": final.content})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
        ]})

        first_token_time = None
        chunks = []
        with client.messages.stream(
            model=MODEL, max_tokens=60, system=SYSTEM_PROMPT,
            tools=TOOLS, messages=messages,
        ) as stream:
            for text in stream.text_stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                chunks.append(text)
        num_llm_calls = 2

    t_end = time.perf_counter()
    full_text = "".join(chunks)
    ttft = (first_token_time - t_start) if first_token_time else (t_end - t_start)
    full_completion = t_end - t_start
    return full_text, ttft, full_completion, num_llm_calls


def fake_tts(text: str) -> bytes:
    delay_s = random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000
    time.sleep(delay_s)
    return text.encode()


def real_tts_stream(tts_ws, text: str) -> tuple[bytes, float]:
    """Send text over an ALREADY-OPEN Deepgram TTS websocket and collect the
    synthesized PCM. Returns (pcm_bytes, time_to_first_byte_seconds).

    The socket being already open is the whole trick: a fresh websocket
    handshake (TLS + auth) costs ~1.3-1.6s on its own, before Deepgram has
    synthesized a single sample. Opening one connection for the whole call
    and reusing it turn-to-turn (see open_tts_stream()) gets first-audio-byte
    down to ~300-400ms — that's the difference between "the AI is booting up
    something" and a reply that feels immediate."""
    t0 = time.perf_counter()
    first_byte_time = None
    chunks = []
    tts_ws.send_text(SpeakV1Text(text=text))
    tts_ws.send_flush()
    for msg in tts_ws:
        if isinstance(msg, (bytes, bytearray)):
            if first_byte_time is None:
                first_byte_time = time.perf_counter()
            chunks.append(msg)
        elif type(msg).__name__ == "SpeakV1Flushed":
            break
    ttfb = (first_byte_time - t0) if first_byte_time else (time.perf_counter() - t0)
    return b"".join(chunks), ttfb


def tts(text: str, tts_ws) -> tuple[bytes, float, bool]:
    """Try real streaming Deepgram TTS over tts_ws when it's open; fall back
    to fake_tts() otherwise (no key, socket never opened, or the call fails
    at runtime — mid-call failure doesn't tear down the socket, just this
    turn). Returns (audio_bytes, tts_seconds, used_real) where tts_seconds
    is time-to-FIRST-byte for the real path (the number that actually gates
    when playback can start), not total synthesis time."""
    if tts_ws is not None:
        try:
            audio, ttfb = real_tts_stream(tts_ws, text)
            return audio, ttfb, True
        except Exception as exc:
            print(f"Deepgram TTS call failed ({exc}) — falling back to simulated TTS.")
    t0 = time.perf_counter()
    audio = fake_tts(text)
    return audio, time.perf_counter() - t0, False


@contextlib.contextmanager
def open_tts_stream():
    """Open ONE persistent Deepgram TTS websocket for the whole call (or a
    no-op null context if Deepgram isn't configured / the handshake fails).
    Callers pass the resulting socket into every run_turn() for the call so
    turns share a warm connection instead of paying handshake cost each
    time."""
    if deepgram is None:
        yield None
        return
    try:
        with deepgram.speak.v1.connect(
            model=TTS_MODEL, encoding=TTS_ENCODING, sample_rate=TTS_SAMPLE_RATE,
        ) as ws:
            yield ws
    except Exception as exc:
        print(f"Deepgram TTS websocket unavailable ({exc}) — using simulated TTS.")
        yield None


def run_turn(user_utterance: str, audio_path: Path | None = None, turn_index: int = 0, tts_ws=None):
    t0 = time.perf_counter()
    transcript = stt(user_utterance, audio_path)
    t1 = time.perf_counter()
    stt_ms = (t1 - t0) * 1000

    reply, ttft, full_completion, num_llm_calls = call_llm_streaming(transcript)
    llm_ttft_ms = ttft * 1000
    llm_full_ms = full_completion * 1000

    audio_bytes, tts_seconds, used_real_tts = tts(reply, tts_ws)
    tts_ms = tts_seconds * 1000

    time_to_first_audio_ms = stt_ms + llm_ttft_ms + tts_ms

    stt_source = f"real Deepgram, model={STT_MODEL}" if (deepgram and audio_path and audio_path.exists()) else "simulated"
    tts_label = "real Deepgram Aura, first-byte" if used_real_tts else "simulated"
    print(f"Transcript ({stt_source}): {transcript}")
    print(f"Reply: {reply}")
    print(f"STT: {stt_ms:.0f}ms | LLM time-to-first-token: {llm_ttft_ms:.0f}ms "
          f"(full completion: {llm_full_ms:.0f}ms, {num_llm_calls} call"
          f"{'s' if num_llm_calls > 1 else ''}) | TTS ({tts_label}): {tts_ms:.0f}ms")
    print(f"TIME TO FIRST AUDIO: {time_to_first_audio_ms:.0f}ms", end="  ")
    print("[WITHIN BUDGET]" if time_to_first_audio_ms <= BUDGET_MS else "[OVER BUDGET]")

    if used_real_tts:
        AUDIO_DIR.mkdir(exist_ok=True)
        out_path = AUDIO_DIR / f"reply_{turn_index}.wav"
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # linear16
            w.setframerate(int(TTS_SAMPLE_RATE))
            w.writeframes(audio_bytes)
        print(f"Reply audio saved to: {out_path}")


if __name__ == "__main__":
    utterances = [
        "What's my account balance?",
        "Can you tell me if my paycheck deposited yet?",
        "I need to report my card as lost.",
    ]
    with open_tts_stream() as tts_ws:
        for i, u in enumerate(utterances, start=1):
            print(f"\n--- Turn: \"{u}\" ---")
            wav_path = AUDIO_DIR / f"turn_{i}.wav"
            run_turn(u, wav_path if wav_path.exists() else None, turn_index=i, tts_ws=tts_ws)

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
#
# The TTS side is a second, sharper example of the same "first byte vs full
# completion" lesson: a fresh TTS websocket handshake costs ~1.3-1.6s before
# any audio exists — reconnecting per turn is what makes a voice agent feel
# like it's booting up an AI tool instead of just talking. open_tts_stream()
# opens ONE connection for the whole call and every turn reuses it, which is
# what gets first-audio-byte down to ~300-400ms. Same principle as streaming
# the LLM: don't pay a one-time cost on every turn.
