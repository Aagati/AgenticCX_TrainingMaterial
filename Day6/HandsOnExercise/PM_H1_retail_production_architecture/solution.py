"""
PM · H1 — Retail: Production Architecture (REFERENCE SOLUTION)

Fuses this morning's three labs into one production-shaped session class,
the same fusion move Day 3's PM·H1 made — and this includes BOTH of AM_H1's
paths, not just native audio:
  - AM_H1's modular pipeline (fake_stt -> REAL streamed Claude call ->
    fake_tts) AND its native-audio Live connection — routed between by
    `_needs_native()`, a genuine production-architecture decision: a plain
    FAQ turn doesn't need a full native-audio session with tools and
    grounding bound to it, so it's cheaper to route it through the light
    modular/Claude path and reserve the native session for turns that
    actually need multimodal input or a tool call.
  - AM_H2's affective dialogue + proactive audio config, on by default for
    the native path
  - AM_H3's function calling (order lookup), Google Search grounding, and
    multimodal image input (a photo of a damaged item for a return)
...and adds this lab's own topic — PRODUCTION ARCHITECTURE:
  - session resumption: capture the server's resumption handle and use it
    to reconnect after a simulated dropped connection instead of starting
    the conversation over
  - a structured, append-only session log (this day's version of the
    audit-trail thread Day 4/5 built for compliance and eval)

NOTE on the two "same idea, different job" pieces this day builds: this
lab routes to the modular path UPFRONT based on what the request needs
(an architecture decision, made before anything fails). PM_H3 routes to
the modular path as a FAILOVER when native is unreachable (a reliability
decision, made after something fails). Same two functions, different
trigger, different topic.

demo_am_recap() at the bottom reproduces AM_H1's timed pipeline-vs-native
comparison and AM_H2's affect-on/off + proactive-check-in demos standalone
— this lab is teachable on its own, without the morning session.
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

    r, g, b = 150, 60, 60  # dull red — stands in for a photo of scuffed packaging
    raw = (b"\x00" + bytes([r, g, b]) * size) * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def fake_stt(text: str) -> str:
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return text


def call_llm_streaming(transcript: str) -> str:
    """Real streamed Claude call — AM_H1's exact call shape."""
    chunks = []
    with anthropic_client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=120,
        thinking={"type": "disabled"},  # see AM_H1 for why this matters at low max_tokens
        system="You are a retail support agent. Reply in short, natural sentences.",
        messages=[{"role": "user", "content": transcript}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    return "".join(chunks)


def fake_tts(text: str) -> str:
    time.sleep(random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000)
    return text


def run_modular_turn(text: str) -> str:
    """AM_H1's 3-hop shape (fake_stt -> real streamed Claude -> fake_tts),
    reused here as PM_H1's cost-routed path for plain FAQ turns that don't
    need tools, grounding, or multimodal input — no reason to pay for a
    full native-audio Live session just to answer a return-policy question."""
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
        order_tool = genai_types.Tool(function_declarations=[GET_ORDER_STATUS_DECL])
        search_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
        kwargs = {
            "response_modalities": ["AUDIO"],
            "system_instruction": "You are a retail support agent. Use get_order_status for order questions.",
            "tools": [order_tool, search_tool],
            "session_resumption": genai_types.SessionResumptionConfig(handle=self.resumption_handle),
        }
        # enable_affect/enable_proactive default True for the main session —
        # the two knobs exist so demo_am_recap() below can toggle them off
        # to show AM_H2's on/off contrast without a second session class.
        if enable_affect:
            kwargs["enable_affective_dialog"] = True
        if enable_proactive:
            kwargs["proactivity"] = genai_types.ProactivityConfig(proactive_audio=True)
        return genai_types.LiveConnectConfig(**kwargs)

    async def _run_turn_async(self, parts: list, image_bytes: bytes | None = None) -> str:
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
        """Like _run_turn_async but with affect/proactivity toggleable and
        no tool/multimodal handling — used only by demo_am_recap() below to
        reproduce AM_H2's on/off contrast without a second session class."""
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
        """AM_H2's silence-gap listen, ported here so this lab can
        demonstrate proactive audio actually firing, not just enable the
        config flag and hope."""
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
        """The architecture decision: does this turn actually need the
        native session's multimodal input, its order-lookup tool, or its
        grounding tool (a plain-FAQ Claude call has no way to answer a
        "what's happening right now" question)? If not, it's cheaper and
        simpler to answer it over the modular path."""
        if image_bytes is not None:
            return True
        if any(order_id in text for order_id in ORDER_DB):
            return True
        lowered = text.lower()
        return any(hint in lowered for hint in GROUNDING_HINT_WORDS)

    def send_turn(self, text: str, image_bytes: bytes | None = None) -> str:
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
        """The point of session resumption: a dropped connection doesn't
        mean starting the conversation over. `send_turn` after this call
        rebuilds `_build_config()` with `self.resumption_handle` already
        set — nothing else about the call site changes."""
        had_handle = self.resumption_handle is not None
        self._record("connection_dropped")
        self._record("reconnect_attempt", using_saved_handle=had_handle)
        self._record("reconnected", using_saved_handle=had_handle)

    def print_log(self):
        print("\n--- session log ---")
        for entry in self.log:
            print(f"  {entry}")


def demo_am_recap():
    """Standalone recap of AM_H1's and AM_H2's core lessons, ported into
    this lab so the whole day is teachable from PM labs alone — none of
    this depends on anything the main scenario above already ran."""

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

    print(session.send_turn("Hi, can you check the status of order ORD-4471?"))
    print(session.send_turn("Here's a photo of the item I want to return.", image_bytes=make_damaged_item_png()))
    print(session.send_turn("Quick one while I'm on hold — what's your standard return window for electronics?"))
    print(session.send_turn("Is there a known shipping delay in my area today?"))  # routes native -> exercises grounding

    session.simulate_dropped_connection_and_reconnect()

    print(session.send_turn("Sorry, we got cut off — is order ORD-4471 still on track?"))

    session.print_log()

    demo_am_recap()

# Expected: turn 1 (mentions ORD-4471) routes "native", triggers a
# "tool_call" log entry for get_order_status (real or simulated) resolving
# to "out for delivery". Turn 2 (has an image) also routes "native" — no
# order tool needed, handled as a return-intake conversation. Turn 3 (plain
# FAQ, no order id, no image, no grounding hint) routes "modular" and is
# answered by a REAL Claude call regardless of whether GEMINI_API_KEY is
# set — this is the one path in this lab that's never simulated. Turn 4
# ("...today?") routes "native" on the grounding-hint match and exercises
# the google_search tool (real citations only with a real key — simulation
# can't fabricate those, same as AM_H3). Between turns 4 and 5,
# simulate_dropped_connection_and_reconnect() logs "connection_dropped" ->
# "reconnect_attempt" -> "reconnected", with using_saved_handle=True ONLY
# if a real native session ever returned a session_resumption_update — in
# full Gemini simulation it stays False throughout, which is itself the
# point: you can't resume a session that was never really opened. Turn 5
# (mentions ORD-4471 again) routes "native" so the resumption path
# actually gets exercised, not silently skipped by the modular route.
#
# demo_am_recap() then reproduces AM_H1's timed modular-vs-native
# comparison and AM_H2's affect-on/off + proactive-check-in demonstrations
# standalone, so an instructor can teach this lab without the morning
# session ever having run.
