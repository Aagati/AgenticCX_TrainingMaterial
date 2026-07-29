"""
AM · H1 — Banking Voice Loop + Latency Measurement (STARTER)

STT tries a REAL Deepgram Nova-3 call first (your TODO 1 below) and TTS
tries a REAL Deepgram Aura streaming call (TODO 4) — both fall back to
their simulated counterpart if DEEPGRAM_API_KEY isn't set, the relevant
model/socket isn't reachable, or there's no matching WAV in sample_audio/
— so this lab runs for every student, key or no key. The LLM call is real
either way, uses Claude's streaming API with tool use (a mock account
ledger — see GET_ACCOUNT_INFO_TOOL/FREEZE_CARD_TOOL above), so "LLM ms"
genuinely measures time-to-first-token rather than full completion time.
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

SYSTEM_PROMPT = (
    "You are a banking phone support agent. Reply in short, natural, "
    "spoken-style sentences — this response will be read aloud by a voice "
    "synthesizer, not displayed as text. No bullet points, no markdown. "
    "Use get_account_info for balance or deposit questions, and freeze_card "
    "when the caller reports their card lost or stolen."
)

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
BUDGET_MS = 1000    #Ideally this would close to ~650ms

AUDIO_DIR = Path(__file__).parent / "sample_audio"
STT_MODEL_PREFERRED = "nova-3"
STT_MODEL_FALLBACK = "nova-2"  # one tier down — cheaper per-minute, still batch-capable
TTS_MODEL = "aura-2-asteria-en"
TTS_ENCODING = "linear16"  # raw PCM — the streaming TTS socket only speaks
TTS_SAMPLE_RATE = "16000"  # linear16/mulaw/alaw, not mp3 (that's REST-only)

# --- Deepgram setup (this is the important init for deepgram SDK, otherwise in case of no key the entire code will break) ---
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
    """
    TODO 1: Wire the real Deepgram call. Open audio_path in binary mode and
    call deepgram.listen.v1.media.transcribe_file(request=<bytes>,
    model=STT_MODEL, smart_format=True). The response shape is
    response.results.channels[0].alternatives[0].transcript — return that
    string.
    """
    with open(audio_path, "b") as f:
        response = deepgram.listen.v1.media.transcribe_file(
            request=f.read(), model=STT_MODEL, smart_format=True
        )

    return response.results.channels[0].alternatives[0].transcript




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
    as a context manager, WITH tool use (tools=TOOLS, system=SYSTEM_PROMPT
    — both given above). As you iterate `for text in stream.text_stream:`,
    record time.perf_counter() the FIRST time you receive a chunk (that's
    time-to-first-token) and accumulate all chunks into the full reply
    text. After the stream ends, call stream.get_final_message() and check
    its .content for a tool_use block:
      - no tool_use -> you already have the spoken reply, num_llm_calls=1
      - tool_use -> call TOOL_FUNCS[tool_use.name](), append the assistant
        turn (final.content) and a user turn with a tool_result block
        (tool_use_id=tool_use.id, content=json.dumps(result)) to messages,
        then make a SECOND streamed call the same way. THAT second stream's
        first-token time and text are what you report — it's the one that
        actually produces the spoken reply. num_llm_calls=2.
    Return (full_text, time_to_first_token_seconds, full_completion_seconds,
    num_llm_calls) — mirrors PM·H1: tool turns cost roughly double the LLM
    time, and the caller should be able to see that in the numbers.
    """
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
                    {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": json.dumps(result)
                    }]})

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
    """
    TODO 3: Simulate TTS time-to-first-audio-byte by sleeping for a random
    duration in TTS_FIRST_BYTE_RANGE_MS, then return a placeholder bytes
    object (e.g. text.encode()) standing in for synthesized audio.
    """
    delay_s = random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000
    time.sleep(delay_s)
    return text.encode()


def real_tts_stream(tts_ws, text: str) -> tuple[bytes, float]:
    """
    TODO 4: Wire the real Deepgram streaming TTS call. tts_ws is an
    ALREADY-OPEN socket (see open_tts_stream() below — one connection is
    opened for the whole call and reused turn-to-turn, which is what makes
    this fast: a fresh handshake alone costs ~1.3-1.6s before any audio
    exists, reused it's ~300-400ms first-byte). Steps:
      1. tts_ws.send_text(SpeakV1Text(text=text)) then tts_ws.send_flush()
      2. Iterate `for msg in tts_ws:` — bytes/bytearray messages are audio
         chunks (record time.perf_counter() the FIRST time you see one,
         that's time-to-first-byte); stop the loop once you get a message
         whose type(msg).__name__ == "SpeakV1Flushed"
      3. Return (b"".join(all audio chunks), time_to_first_byte_seconds)
    """
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
    """Given — tries real_tts_stream() over tts_ws when it's open; falls
    back to fake_tts() otherwise (no key, socket never opened, or the call
    fails at runtime). Returns (audio_bytes, tts_seconds, used_real) where
    tts_seconds is time-to-FIRST-byte for the real path, not total
    synthesis time — same "first vs full" principle as the LLM stage."""
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
    """Given — opens ONE persistent Deepgram TTS websocket for the whole
    call (or a no-op null context if Deepgram isn't configured / the
    handshake fails). Reusing a warm connection across turns instead of
    reconnecting per turn is the actual latency win — see real_tts_stream's
    docstring."""
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
    """
    TODO 5: Time each stage with time.perf_counter():
      - STT: time stt(user_utterance, audio_path) — NOT fake_stt() directly,
        so a turn with a matching WAV file goes through real Deepgram
      - LLM: call call_llm_streaming(); it now returns 4 values — use the
        returned ttft directly (already measured internally), and also
        report full_completion and num_llm_calls for comparison
      - TTS: call tts(reply, tts_ws) — NOT fake_tts() directly, so a call
        with an open tts_ws goes through real Deepgram. It returns
        (audio_bytes, tts_seconds, used_real_tts); tts_seconds is already
        measured for you, no extra perf_counter needed here.
    Compute TIME TO FIRST AUDIO = stt_ms + llm_ttft_ms + tts_ms (this is
    the number that determines whether the customer perceives the agent as
    responsive — NOT stt_ms + llm_full_completion_ms + tts_ms).
    Print a breakdown showing STT, LLM time-to-first-token (full completion
    AND num_llm_calls — tool turns should show ~2 calls and noticeably
    higher LLM time), TTS, and whether TIME TO FIRST AUDIO is within
    BUDGET_MS. If used_real_tts, also save audio_bytes to
    AUDIO_DIR/f"reply_{turn_index}.wav" as a proper mono 16-bit WAV (use
    the wave module — sample rate is int(TTS_SAMPLE_RATE)) and print the
    saved path.
    """
    t0 = time.perf_counter()
    transcript = stt(user_utterance, audio_path)

    t1 = time.perf_counter()
    stt_ms = (t1 - t0) * 1000

    reply, ttft, full_completion, num_llm_calls = call_llm_streaming(transcript)
    llm_ttft_ms = ttft * 100
    llm_full_ms = full_completion * 1000

    audio_bytes, tts_seconds, used_real_tts = tts(reply, tts_ws)
    tts_ms = tts_seconds * 1000

    time_to_first_audio_ms = stt_ms + llm_ttft_ms + tts_ms

    stt_source = f"real Deepgram, model={STT_MODEL}" if (deepgram and audio_path and audio_path.exists()) else "simulated"
    tts_label = "real Deepgram Aura Model first byte" if used_real_tts else "simulated"
    print(f"Transcript ({stt_source}): {transcript}")
    print(f"Reply: {reply}")
    print(f"STT milliseconds: {stt_ms:.0f}ms, {num_llm_calls} calls")
    print(f"Full Completion: {llm_full_ms:.0f}ms {num_llm_calls} call")
    print(f"TIME TO FIRST AUDIO: {time_to_first_audio_ms:.0f}ms", end="")




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

# To exercise the REAL Deepgram path instead of the simulated one: set
# DEEPGRAM_API_KEY in .env, `pip install deepgram-sdk`, and drop up to 3
# short (<10s) mono WAV files into a sample_audio/ folder next to this
# script, named turn_1.wav, turn_2.wav, turn_3.wav (e.g. record with Windows
# Voice Recorder). No WAVs / no key -> falls back to the simulation, no
# code changes needed either way.
