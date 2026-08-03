"""
PM · H1 — Retail: Production Architecture (STARTER)

Fuses BOTH of AM_H1's paths (modular Claude pipeline + native Gemini Live)
+ AM_H2 (affective/proactive config) + AM_H3 (tool calling + grounding +
multimodal input) into one session class, then adds session resumption +
a structured audit log. The modular path is a REAL streamed Claude call
regardless of Gemini key status; the native path is real-if-key with a
simulated fallback — same contract as every AM lab this morning.

This lab routes to modular UPFRONT based on what a turn needs (an
architecture decision). PM_H3 routes to modular as a FAILOVER when native
is unreachable (a reliability decision). Same two functions, different
trigger, different topic.

demo_am_recap() at the bottom (fully given, exercises your TODOs) is a
standalone recap of AM_H1's timed pipeline-vs-native comparison and AM_H2's
affect-on/off + proactive-check-in demos — the point is this lab is
teachable on its own, without the morning session, once your TODOs pass.
"""

import asyncio
import json
import os
import random
import struct
import sys
import time
import zlib
from pathlib import Path

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

MULTIMODAL_LIVE_MODEL = "gemini-3.1-flash-live-preview"

# Optional --voice flow only: real mic-in/speaker-out duplex loop, as a
# contrast to every other turn in this lab (which sends TEXT and, on the
# native route, gets audio back — never real mic input). pyaudio is an
# optional dependency; its absence must not break the scripted default run.
try:
    import pyaudio
except ImportError:
    pyaudio = None

VOICE_SEND_RATE = 16000  # Live API requires 16-bit PCM, 16kHz, mono on the way in
VOICE_RECV_RATE = 24000  # Live API returns 16-bit PCM, 24kHz, mono on the way out
VOICE_CHUNK = 1024

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "order_data.json") as f:
    ORDER_DB = json.load(f)

GROUNDING_HINT_WORDS = ("today", "current", "right now", "outage", "delay", "live", "status update")

GET_ORDER_STATUS_DECL = {
    "name": "get_order_status",
    "description": "Look up a retail order's current status by order id.",
    "parameters": {
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
    },
}


def get_order_status(order_id: str) -> dict:
    return ORDER_DB.get(order_id, {"error": "order not found"})


def make_damaged_item_png(size: int = 64) -> bytes:
    """Given — same pure-stdlib PNG generator as AM_H3, standing in for a
    photo of a damaged item attached to a return request."""
    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(
            ">I", zlib.crc32(chunk_type + data)
        )

    r, g, b = 150, 60, 60
    raw = (b"\x00" + bytes([r, g, b]) * size) * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def fake_stt(text: str) -> str:
    """Given — same simulated STT draw as AM_H1."""
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return text


def call_llm_streaming(transcript: str) -> str:
    """
    TODO 0: A REAL streamed Claude call — AM_H1's exact shape. Use
    client.messages.stream() as a context manager (model=CLAUDE_MODEL,
    max_tokens=120, thinking={"type": "disabled"} — see AM_H1 for why
    that matters at low max_tokens, system=a short retail-agent prompt,
    messages=[{"role": "user", "content": transcript}]). Accumulate
    stream.text_stream into the full reply text and return it.
    """
    chunks = []
    with anthropic_client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=120,
        thinking={"type": "disabled"},
        system="You are a retail support agent. Reply in short, natural sentences.",
        messages=[{"role": "user", "content": transcript}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    return "".join(chunks)


def fake_tts(text: str) -> str:
    """Given — same simulated TTS draw as AM_H1."""
    time.sleep(random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000)
    return text


def run_modular_turn(text: str) -> str:
    """Given — AM_H1's 3-hop shape, reused here as the cost-routed path
    for plain FAQ turns that don't need tools, grounding, or multimodal
    input."""
    transcript = fake_stt(text)
    reply = call_llm_streaming(transcript)
    fake_tts(reply)
    return reply


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _vertex_client import get_genai_client

genai_client, genai_types = get_genai_client()
if genai_client is None:
    print("No working Gemini credentials — session will run in simulation.")


class RetailSupportSession:
    """One production session: native audio + affect/proactivity + tools +
    grounding + multimodal input + session resumption, with a structured
    audit log threaded through every step."""

    def __init__(self):
        self.log = []
        self.resumption_handle = None
        self.real = genai_client is not None

    def _record(self, event_type: str, **fields) -> dict:
        entry = {"t": round(time.perf_counter(), 3), "event": event_type, **fields}
        self.log.append(entry)
        return entry

    def _build_config(self, enable_affect: bool = True, enable_proactive: bool = True):
        """
        TODO 1: Build a LiveConnectConfig combining everything from this
        morning: response_modalities=["AUDIO"], tools=[a Tool wrapping
        GET_ORDER_STATUS_DECL, a Tool wrapping GoogleSearch()] (AM_H3), and
        session_resumption=SessionResumptionConfig(handle=
        self.resumption_handle) — this lab's own new piece. Then, IF
        enable_affect, also set enable_affective_dialog=True (AM_H2); IF
        enable_proactive, also set proactivity=ProactivityConfig(
        proactive_audio=True) (AM_H2). The two params default True for the
        main session — they exist so demo_am_recap() can toggle them off
        to show AM_H2's on/off contrast without a second session class.
        """
        order_tool = genai_types.Tool(function_declarations=[GET_ORDER_STATUS_DECL])
        search_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
        kwargs = {
            "response_modalities": ["AUDIO"],
            "system_instruction": "You are a retail support agent. Use get_order_status for order questions.",
            "tools": [order_tool, search_tool],
            "session_resumption": genai_types.SessionResumptionConfig(handle=self.resumption_handle),
        }
        if enable_affect:
            kwargs["enable_affective_dialog"] = True
        if enable_proactive:
            kwargs["proactivity"] = genai_types.ProactivityConfig(proactive_audio=True)
        return genai_types.LiveConnectConfig(**kwargs)

    async def _run_turn_async(self, parts: list, image_bytes: bytes | None = None) -> str:
        """
        TODO 2: Open the session with self._build_config(). If image_bytes,
        send it FIRST via send_realtime_input (AM_H3's multimodal pattern),
        then send `parts` via send_client_content(turn_complete=True).
        Iterate session.receive():
          - message.session_resumption_update — if .resumable, save
            .new_handle into self.resumption_handle and self._record(...).
          - message.tool_call — for each function call in
            .function_calls, execute get_order_status locally, self._record
            the tool_call, and reply with session.send_tool_response(...)
            (map result to the call's .id). `continue` the loop after —
            tool_call messages don't carry server_content.
          - otherwise, message.server_content: accumulate any model_turn
            text parts, break when turn_complete.
        Return the joined reply text.
        """
        config = self._build_config()
        reply_parts = []
        async with genai_client.aio.live.connect(model=MULTIMODAL_LIVE_MODEL, config=config) as session:
            if image_bytes:
                await session.send_realtime_input(media=genai_types.Blob(data=image_bytes, mime_type="image/png"))
            await session.send_client_content(turns={"parts": parts}, turn_complete=True)

            async for message in session.receive():
                update = message.session_resumption_update
                if update and update.resumable:
                    self.resumption_handle = update.new_handle
                    self._record("session_resumption_update", handle_saved=bool(self.resumption_handle))

                if message.tool_call:
                    for fc in message.tool_call.function_calls:
                        args = dict(fc.args)
                        result = get_order_status(**args) if fc.name == "get_order_status" else {"error": "unknown tool"}
                        self._record("tool_call", name=fc.name, args=args, result=result)
                        await session.send_tool_response(
                            function_responses=[genai_types.FunctionResponse(id=fc.id, name=fc.name, response=result)]
                        )
                    continue

                sc = message.server_content
                if sc is None:
                    continue
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.text:
                            reply_parts.append(part.text)
                if sc.turn_complete:
                    break

        return "".join(reply_parts) or "(audio-only reply)"

    async def _run_bare_turn_async(self, text: str, enable_affect: bool, enable_proactive: bool) -> str:
        """
        TODO 6: Like _run_turn_async but with no tool/multimodal handling
        (just build self._build_config(enable_affect, enable_proactive),
        open a session, send `text` as a single-part turn, collect
        model_turn text parts until turn_complete). Used only by
        demo_am_recap() below to reproduce AM_H2's on/off contrast without
        a second session class.
        """
        config = self._build_config(enable_affect=enable_affect, enable_proactive=enable_proactive)
        reply_parts = []
        async with genai_client.aio.live.connect(model=MULTIMODAL_LIVE_MODEL, config=config) as session:
            await session.send_client_content(turns={"parts": [{"text": text}]}, turn_complete=True)
            async for message in session.receive():
                sc = message.server_content
                if sc is None:
                    continue
                if sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.text:
                            reply_parts.append(part.text)
                if sc.turn_complete:
                    break
        return "".join(reply_parts) or "(audio-only reply)"

    async def _listen_for_proactive_async(self, opening_text: str, timeout_s: float = 6.0) -> bool:
        """
        TODO 7: AM_H2's silence-gap listen, ported here so this lab can
        demonstrate proactive audio actually firing. build_config(
        enable_affect=True, enable_proactive=True), open a session, send
        opening_text as a turn, drain the direct reply (loop receive()
        until turn_complete). THEN, with no further input, wrap another
        receive() loop in `async with asyncio.timeout(timeout_s):` and
        return True the moment any message with server_content arrives
        unprompted. Catch TimeoutError and return False otherwise.
        """
        config = self._build_config(enable_affect=True, enable_proactive=True)
        async with genai_client.aio.live.connect(model=MULTIMODAL_LIVE_MODEL, config=config) as session:
            await session.send_client_content(turns={"parts": [{"text": opening_text}]}, turn_complete=True)
            async for message in session.receive():
                if message.server_content and message.server_content.turn_complete:
                    break
            try:
                async with asyncio.timeout(timeout_s):
                    async for message in session.receive():
                        if message.server_content:
                            return True
            except TimeoutError:
                pass
        return False

    @staticmethod
    def _needs_native(text: str, image_bytes: bytes | None) -> bool:
        """
        TODO 3: Return True if image_bytes is not None (multimodal input
        needs the native session), OR if any order id in ORDER_DB appears
        as a substring of text (the order-lookup tool only exists on the
        native session), OR if any GROUNDING_HINT_WORDS appears in
        text.lower() (a plain Claude call has no way to answer a
        "what's happening right now" question). Otherwise return False —
        this turn can be answered by the cheaper modular/Claude path.
        """
        if image_bytes is not None:
            return True
        if any(order_id in text for order_id in ORDER_DB):
            return True
        lowered = text.lower()
        return any(hint in lowered for hint in GROUNDING_HINT_WORDS)

    def send_turn(self, text: str, image_bytes: bytes | None = None) -> str:
        """
        TODO 4: Decide route = "native" or "modular" via self._needs_native().
        self._record("turn_sent", ..., route=route). If route == "modular",
        call run_modular_turn(text), record the reply with path="modular",
        real=True (it's always a real Claude call), and return it.
        Otherwise, dispatch to the real async native turn when Gemini is
        configured (self.real); fall back to _simulated_reply() otherwise.
        Tag every "turn_reply"/"turn_failed" record with path="native" on
        this branch.
        """
        route = "native" if self._needs_native(text, image_bytes) else "modular"
        self._record("turn_sent", text=text, has_image=image_bytes is not None, route=route)

        if route == "modular":
            reply = run_modular_turn(text)
            self._record("turn_reply", reply=reply, real=True, path="modular")
            return reply

        if self.real:
            try:
                reply = asyncio.run(self._run_turn_async([{"text": text}], image_bytes))
                self._record("turn_reply", reply=reply, real=True, path="native")
                return reply
            except Exception as exc:
                self._record("turn_failed", error=str(exc))
                print(f"Gemini Live call failed ({exc}) — falling back to simulated reply.")

        reply = self._simulated_reply(text, image_bytes)
        self._record("turn_reply", reply=reply, real=False, path="native")
        return reply

    def _simulated_reply(self, text: str, image_bytes: bytes | None) -> str:
        for order_id in ORDER_DB:
            if order_id in text:
                info = get_order_status(order_id)
                self._record("tool_call", name="get_order_status", args={"order_id": order_id}, result=info)
                return f"(simulated) Order {order_id} is {info['status']}."
        if image_bytes:
            return "(simulated) Thanks for the photo — I can see the item, let's get a return started."
        return "(simulated) Can you tell me your order number?"

    def simulate_dropped_connection_and_reconnect(self):
        """
        TODO 5: Log three events in order: "connection_dropped",
        "reconnect_attempt" (with using_saved_handle=bool(self.
        resumption_handle)), then "reconnected" (same flag). No actual
        socket work needed — the NEXT send_turn() call already rebuilds
        _build_config() with self.resumption_handle set, so reconnecting is
        just "call send_turn again."
        """
        had_handle = self.resumption_handle is not None
        self._record("connection_dropped")
        self._record("reconnect_attempt", using_saved_handle=had_handle)
        self._record("reconnected", using_saved_handle=had_handle)

    def print_log(self):
        print("\n--- session log ---")
        for entry in self.log:
            print(f"  {entry}")

    # ---- Optional alternative flow: real duplex voice (mic in / speaker out) ----
    # Nothing above this line uses a real microphone or speaker — every turn in
    # this lab sends TEXT, and only the native route gets real audio BACK. This
    # is what a real voice call adds: continuous audio in, streamed playback out,
    # and handling for the two message types a text turn never produces
    # (tool_call arriving mid-audio-stream, and "interrupted" for barge-in).

    async def _mic_to_session(self, session, mic_stream, stop_event):
        """Given — streams raw mic audio into the session chunk by chunk.
        Production counterpart to send_client_content(text=...) above — audio
        goes in as it's captured, never buffered into one blob first."""
        while not stop_event.is_set():
            chunk = await asyncio.to_thread(mic_stream.read, VOICE_CHUNK, exception_on_overflow=False)
            await session.send_realtime_input(
                audio=genai_types.Blob(data=chunk, mime_type=f"audio/pcm;rate={VOICE_SEND_RATE}")
            )

    async def _session_to_speaker(self, session, speaker_stream, stop_event):
        """
        TODO 8: Play audio deltas as they arrive (not buffer-then-play,
        unlike AM_H1's save-to-wav-at-the-end) and handle the two message
        types a text-only turn never produces:
          - message.tool_call — same pattern as _run_turn_async: for each
            function call, run get_order_status(**args) (or an
            {"error": "unknown tool"} dict for anything else), self._record
            the tool_call, and reply with session.send_tool_response(...).
            `continue` afterward.
          - message.server_content.interrupted — the customer started
            talking while the agent was still speaking (barge-in). Just
            self._record("voice_barge_in") and `continue` — the point is
            to NOTICE it, actual playback-buffer flushing is a stretch goal.
          - message.server_content.model_turn parts with .inline_data.data —
            write the raw bytes to speaker_stream via
            asyncio.to_thread(speaker_stream.write, ...) so playback doesn't
            block the receive loop.
        Loop until stop_event is set.
        """
        async for message in session.receive():
            if stop_event.is_set():
                break

            if message.tool_call:
                for fc in message.tool_call.function_calls:
                    args = dict(fc.args)
                    result = get_order_status(**args) if fc.name == "get_order_status" else {"error": "unknown tool"}
                    self._record("tool_call", name=fc.name, args=args, result=result)
                    await session.send_tool_response(
                        function_responses=[genai_types.FunctionResponse(id=fc.id, name=fc.name, response=result)]
                    )
                continue

            sc = message.server_content
            if sc is None:
                continue
            if sc.interrupted:
                self._record("voice_barge_in")
                continue
            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        await asyncio.to_thread(speaker_stream.write, part.inline_data.data)

    async def _voice_loop_async(self, duration_s: float):
        """Given — opens the mic/speaker streams, runs _mic_to_session and
        _session_to_speaker concurrently for duration_s seconds, cleans up."""
        pa = pyaudio.PyAudio()
        mic_stream = pa.open(format=pyaudio.paInt16, channels=1, rate=VOICE_SEND_RATE,
                              input=True, frames_per_buffer=VOICE_CHUNK)
        speaker_stream = pa.open(format=pyaudio.paInt16, channels=1, rate=VOICE_RECV_RATE, output=True)
        stop_event = asyncio.Event()
        config = self._build_config()  # same tools + resumption + affect/proactivity as the text route
        self._record("voice_loop_started")
        try:
            async with genai_client.aio.live.connect(model=MULTIMODAL_LIVE_MODEL, config=config) as session:
                print(f"Voice loop live for {duration_s:.0f}s — talk into your mic now.")
                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            self._mic_to_session(session, mic_stream, stop_event),
                            self._session_to_speaker(session, speaker_stream, stop_event),
                        ),
                        timeout=duration_s,
                    )
                except asyncio.TimeoutError:
                    stop_event.set()
        finally:
            mic_stream.close()
            speaker_stream.close()
            pa.terminate()
            self._record("voice_loop_ended")

    def run_live_voice_demo(self, duration_s: float = 20.0):
        """Given — optional alternative flow, NOT part of the scripted
        __main__ turns below (those stay text-only so the lab runs on any
        laptop with no mic). Run explicitly with `python starter.py --voice`.
        Needs `pip install pyaudio` (+ system portaudio) and a real
        GEMINI_API_KEY; degrades to a clear message otherwise."""
        if pyaudio is None:
            print("pyaudio not installed — run `pip install pyaudio` to try --voice.")
            return
        if not self.real:
            print("No Gemini credentials — --voice needs a real session, nothing to simulate here.")
            return
        asyncio.run(self._voice_loop_async(duration_s))


def demo_am_recap():
    """Given — standalone recap of AM_H1's and AM_H2's core lessons,
    ported into this lab so the whole day is teachable from PM labs alone.
    Exercises the TODOs above; nothing new to fill in here."""

    print("\n=== AM recap 1/3 — pipeline vs. native, timed (AM_H1) ===")
    text = "What's your standard shipping cutoff time for next-day delivery?"

    t0 = time.perf_counter()
    modular_reply = run_modular_turn(text)
    modular_ms = (time.perf_counter() - t0) * 1000
    print(f"  modular (3-hop, real Claude): {modular_ms:.0f}ms")
    print(f"    {modular_reply[:100]}")

    recap = RetailSupportSession()
    t0 = time.perf_counter()
    if recap.real:
        try:
            native_reply = asyncio.run(recap._run_bare_turn_async(text, True, True))
        except Exception as exc:
            print(f"  Gemini Live call failed ({exc}) — using simulated native reply.")
            native_reply = recap._simulated_reply(text, None)
    else:
        native_reply = recap._simulated_reply(text, None)
    native_ms = (time.perf_counter() - t0) * 1000
    print(f"  native  (1-hop, {'real' if recap.real else 'simulated'}): {native_ms:.0f}ms")
    print(f"    {native_reply[:100]}")

    print("\n=== AM recap 2/3 — affective dialogue on/off (AM_H2) ===")
    distressed = "This is SO frustrating — my package never arrived and nobody's helping me!"
    recap2 = RetailSupportSession()
    if recap2.real:
        try:
            off_reply = asyncio.run(recap2._run_bare_turn_async(distressed, False, False))
            on_reply = asyncio.run(recap2._run_bare_turn_async(distressed, True, False))
        except Exception as exc:
            print(f"  Gemini Live call failed ({exc}) — using simulated replies.")
            off_reply = on_reply = "(simulated) Can you tell me your order number?"
    else:
        off_reply = "(simulated) Can you tell me your order number?"
        on_reply = "(simulated) I'm sorry to hear that — let's get this sorted out right away. Can you share your order number?"
    print(f"  affect OFF: {off_reply[:120]}")
    print(f"  affect ON:  {on_reply[:120]}")

    print("\n=== AM recap 3/3 — proactive audio check-in (AM_H2) ===")
    recap3 = RetailSupportSession()
    if recap3.real:
        try:
            proactive = asyncio.run(recap3._listen_for_proactive_async(distressed))
        except Exception as exc:
            print(f"  Gemini Live call failed ({exc}) — using simulated proactivity rule.")
            proactive = random.random() < 0.7
    else:
        proactive = random.random() < 0.7
    print(f"  unprompted check-in during silence gap: {proactive} ({'real' if recap3.real else 'simulated'})")


if __name__ == "__main__":
    session = RetailSupportSession()

    if "--voice" in sys.argv:
        session.run_live_voice_demo()
        session.print_log()
        sys.exit(0)

    print(session.send_turn("Hi, can you check the status of order ORD-4471?"))
    print(session.send_turn("Here's a photo of the item I want to return.", image_bytes=make_damaged_item_png()))
    print(session.send_turn("Quick one while I'm on hold — what's your standard return window for electronics?"))
    print(session.send_turn("Is there a known shipping delay in my area today?"))  # routes native -> exercises grounding

    session.simulate_dropped_connection_and_reconnect()

    print(session.send_turn("Sorry, we got cut off — is order ORD-4471 still on track?"))

    session.print_log()

    demo_am_recap()
