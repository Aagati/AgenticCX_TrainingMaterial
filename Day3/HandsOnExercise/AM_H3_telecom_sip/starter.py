"""
AM · H3 — Telecom SIP Call State Machine (STARTER)

Call events stay simulated (see README) — but the agent's spoken lines
(greeting, replies, transfer message) are synthesized through a REAL
Deepgram Aura TTS stream when DEEPGRAM_API_KEY is set, saved as WAVs under
sample_audio_h3/, so a live demo has actual audio to play back. No key? The
given speak() helper below falls back to text-only, silently — your
handle_event() logic (the actual TODO) doesn't need to know or care which
path it's on.
"""

import contextlib
import os
import wave
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

STATES = ["RINGING", "ANSWERED", "IN_PROGRESS", "ENDED"]

AUDIO_DIR = Path(__file__).parent / "sample_audio_h3"
TTS_MODEL = "aura-2-asteria-en"
TTS_ENCODING = "linear16"
TTS_SAMPLE_RATE = "16000"

deepgram = None
SpeakV1Text = None

if os.environ.get("DEEPGRAM_API_KEY"):
    try:
        from deepgram import DeepgramClient
        from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

        deepgram = DeepgramClient(api_key=os.environ["DEEPGRAM_API_KEY"])
    except Exception as exc:
        print(f"Deepgram setup failed ({exc}) — agent audio disabled, text-only.")
        deepgram = None


@contextlib.contextmanager
def open_tts_stream():
    """Given — one persistent Deepgram TTS websocket for the whole call,
    or a no-op null context if Deepgram isn't configured / the handshake
    fails. Only the CONNECT step is guarded — once open, any exception
    from your handle_event() code inside the `with` block propagates
    normally, it isn't swallowed here."""
    if deepgram is None:
        yield None
        return
    try:
        cm = deepgram.speak.v1.connect(
            model=TTS_MODEL, encoding=TTS_ENCODING, sample_rate=TTS_SAMPLE_RATE,
        )
        ws = cm.__enter__()
    except Exception as exc:
        print(f"Deepgram TTS websocket unavailable ({exc}) — text-only.")
        yield None
        return
    try:
        yield ws
    finally:
        cm.__exit__(None, None, None)


_tts_ws = None
_clip_index = 0


def speak(label: str, text: str):
    """Given — print the agent's line and, when a real TTS socket is
    open, synthesize it and save the clip to sample_audio_h3/NN_label.wav.
    Call this instead of print() for anything the AGENT says."""
    global _clip_index
    print(f"  -> {label}: \"{text}\"")
    if _tts_ws is None:
        return
    try:
        _tts_ws.send_text(SpeakV1Text(text=text))
        _tts_ws.send_flush()
        chunks = []
        for msg in _tts_ws:
            if isinstance(msg, (bytes, bytearray)):
                chunks.append(msg)
            elif type(msg).__name__ == "SpeakV1Flushed":
                break
        AUDIO_DIR.mkdir(exist_ok=True)
        _clip_index += 1
        slug = label.lower().replace(" ", "_")
        out_path = AUDIO_DIR / f"{_clip_index:02d}_{slug}.wav"
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # linear16
            w.setframerate(int(TTS_SAMPLE_RATE))
            w.writeframes(b"".join(chunks))
        print(f"     (audio saved to {out_path.relative_to(Path(__file__).parent)})")
    except Exception as exc:
        print(f"Deepgram TTS call failed ({exc}) — text-only for this line.")


def simulate_incoming_call():
    """Provided — yields a sequence of call events, like a SIP provider would."""
    yield {"type": "ring"}
    yield {"type": "answer"}
    yield {"type": "speech", "text": "Hi, I want to check my data usage this month."}
    yield {"type": "speech", "text": "Also, what's my current plan?"}
    yield {"type": "dtmf", "digit": "0"}
    yield {"type": "hangup"}


def call_llm(transcript: str) -> str:
    response = client.messages.create(
        model=MODEL, max_tokens=60,
        system=(
            "You are a telecom phone support agent. Reply in short, natural, "
            "spoken-style sentences suitable for text-to-speech. No markdown."
        ),
        messages=[{"role": "user", "content": transcript}],
    )
    # content[0] isn't guaranteed to be the text block — this model can
    # return a ThinkingBlock ahead of it, which has no .text attribute.
    return next(b.text for b in response.content if b.type == "text")


def handle_event(state: str, event: dict):
    """
    TODO: Implement the state machine transitions.
      - state RINGING + event "ring" -> stay RINGING, action: None
      - state RINGING + event "answer" -> ANSWERED, action: speak() a greeting
      - state ANSWERED + event "speech" -> IN_PROGRESS, action: call_llm() and speak() the reply
      - state IN_PROGRESS + event "speech" -> stay IN_PROGRESS, action: call_llm() and speak() the reply
      - state IN_PROGRESS (or ANSWERED) + event "dtmf" with digit "0" ->
        stay in current state, action: speak() "Transferring to a human agent."
        (don't call the LLM for this)
      - any state + event "hangup" -> ENDED, action: print "Call ended."
    Use the given speak(label, text) helper (not print) for anything the
    AGENT says — it prints the line AND synthesizes real audio into
    sample_audio_h3/ when DEEPGRAM_API_KEY is set. Customer lines (from the
    "speech" event's "text") can stay a plain print — they represent
    already-transcribed STT output, not agent audio to synthesize.
    Return the new state.
    """
    etype = event["type"]
    if etype == "hangup":
        print(" -> Call ended.")
        return "ENDED"

    if etype == "ring" and state == "RINGING":
        return "RINGING"

    if etype == "answer" and state == "RINGING":
        speak("Greetings! Thanks for calling how can I help you today?")
        return "ANSWERED"

    if etype == "dtmf" and event.get("digit") == "0" and state in ("ANSWERED", "IN_PROGRESS"):
        speak("Transfer", "Transferring you to a human agent now.")
        return state

    if etype == "speech" and state in ("ANSWERED", "IN_PROGRESS"):
        reply = call_llm(event["text"])
        print(f" -> Customer: \"{event['text']}\"")
        speak("Agent", reply)
        return "IN_PROGRESS"
    print(f" -> (unhandled event {etype} in state {state})")
    return state


if __name__ == "__main__":
    with open_tts_stream() as ws:
        _tts_ws = ws
        state = "RINGING"
        print(f"[{state}]")
        for event in simulate_incoming_call():
            state = handle_event(state, event)
            print(f"[{state}]  (event: {event['type']})")

# To hear the agent's side for real: set DEEPGRAM_API_KEY in .env and
# `pip install deepgram-sdk` — a correct handle_event() will synthesize
# the greeting, both replies, and the transfer line into sample_audio_h3/.
# No key -> falls back to text-only, no code changes needed either way.
