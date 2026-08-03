"""
PM · H3 — Insurance: Latency & Reliability + Compliance (STARTER)

The day's capstone: one insurance claims call, six production concerns,
one call_log. Native audio tries a REAL Gemini Live call first and fails
over to a modular pipeline (real streamed Claude call) on any failure —
including a simulated unreachable draw when no key is set, so this lab
runs for every student either way — timed and logged either way. On top
of that: disclosure/consent/erasure compliance, multimodal redaction,
proactive-turn attribution, barge-in, and a closing call summary that
aggregates the whole log into one reliability+compliance report.
"""

import asyncio
import hashlib
import json
import os
import random
import sys
import time
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

# Current native-audio-dialog model id as of this writing — check
# ai.google.dev/gemini-api/docs/models for a newer one before class.
NATIVE_AUDIO_MODEL = "gemini-live-2.5-flash-native-audio"

STT_LATENCY_RANGE_MS = (120, 220)
TTS_FIRST_BYTE_RANGE_MS = (60, 100)
LIVE_CONNECT_FAIL_RATE = 0.25  # simulated: fraction of turns where native is treated as unreachable

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "compliance_policy.json") as f:
    COMPLIANCE_POLICY = json.load(f)

DISCLOSURE_TEXT = COMPLIANCE_POLICY["disclosure_text"]
ERASURE_KEYWORDS = tuple(COMPLIANCE_POLICY["erasure_keywords"])
CONSENT_REFUSAL_MARKERS = tuple(COMPLIANCE_POLICY["consent_refusal_markers"])

SYSTEM_PROMPT = "You are an insurance claims agent. Reply in short spoken sentences."

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _vertex_client import get_genai_client, save_pcm_wav

AUDIO_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_audio_out")

genai_client, genai_types = get_genai_client(location="us-central1")
if genai_client is None:
    print("No working Gemini credentials — every turn will use the modular fallback.")


# ---------------------------------------------------------------------
# Modular fallback pipeline — given.
# ---------------------------------------------------------------------

def fake_stt(user_utterance: str) -> str:
    time.sleep(random.uniform(*STT_LATENCY_RANGE_MS) / 1000)
    return user_utterance


def call_llm_streaming(transcript: str) -> str:
    chunks = []
    with anthropic_client.messages.stream(
        model=CLAUDE_MODEL, max_tokens=60,
        # claude-sonnet-5 defaults to extended thinking on; with a budget
        # this small the model can burn the ENTIRE max_tokens on a thinking
        # block and hit stop_reason="max_tokens" with zero text emitted —
        # disabling it keeps the budget going to the spoken reply.
        thinking={"type": "disabled"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
    return "".join(chunks)


def fake_tts(text: str) -> str:
    time.sleep(random.uniform(*TTS_FIRST_BYTE_RANGE_MS) / 1000)
    return text


def run_modular_fallback_turn(user_utterance: str) -> str:
    transcript = fake_stt(user_utterance)
    reply = call_llm_streaming(transcript)
    fake_tts(reply)
    return reply


async def _try_connect_native(user_utterance: str) -> dict:
    config = genai_types.LiveConnectConfig(response_modalities=["AUDIO"], system_instruction=SYSTEM_PROMPT)
    reply_parts = []
    audio_bytes = bytearray()
    async with genai_client.aio.live.connect(model=NATIVE_AUDIO_MODEL, config=config) as session:
        await session.send_client_content(turns={"parts": [{"text": user_utterance}]}, turn_complete=True)
        async for message in session.receive():
            sc = message.server_content
            if sc is None:
                continue
            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.text:
                        reply_parts.append(part.text)
                    if part.inline_data and part.inline_data.data:
                        audio_bytes.extend(part.inline_data.data)
            if sc.turn_complete:
                break
    audio_path = None
    if audio_bytes:
        fname = f"native_{int(time.time() * 1000)}.wav"
        audio_path = save_pcm_wav(bytes(audio_bytes), os.path.join(AUDIO_OUT_DIR, fname))
    return {"reply": "".join(reply_parts) or "(audio-only reply)", "audio_path": audio_path}


def run_resilient_turn(user_utterance: str, call_log: list) -> dict:
    """
    TODO 1: If genai_client is not None AND random.random() >
    LIVE_CONNECT_FAIL_RATE (i.e. this simulated draw says native is
    reachable), time it: t0 = time.perf_counter(), try _try_connect_native()
    inside a try/except. On success, compute latency_ms = round((
    time.perf_counter() - t0) * 1000), append {"event": "turn_served",
    "path": "native", "latency_ms": latency_ms, "audio_path": ...} to
    call_log and return {"reply": ..., "path": "native", "audio_path": ...,
    "latency_ms": latency_ms}. On exception, append {"event":
    "native_failed", "error": str(exc)} and fall through. Otherwise (or
    after a native failure): append {"event": "failover_to_modular"}, time
    and call run_modular_fallback_turn() the same way, append {"event":
    "turn_served", "path": "modular", "latency_ms": latency_ms}, and return
    {"reply": ..., "path": "modular", "audio_path": None, "latency_ms":
    latency_ms}. The latency numbers are what justify caring about
    failover at all — don't skip them.
    """
    if genai_client is not None and random.random() > LIVE_CONNECT_FAIL_RATE:
        t0 = time.perf_counter()
        try:
            native = asyncio.run(_try_connect_native(user_utterance))
            latency_ms = round((time.perf_counter() - t0) * 1000)
            call_log.append({
                "event": "turn_served", "path": "native",
                "latency_ms": latency_ms, "audio_path": native["audio_path"],
            })
            return {"reply": native["reply"], "path": "native", "audio_path": native["audio_path"], "latency_ms": latency_ms}
        except Exception as exc:
            call_log.append({"event": "native_failed", "error": str(exc)})

    call_log.append({"event": "failover_to_modular"})
    t0 = time.perf_counter()
    reply = run_modular_fallback_turn(user_utterance)
    latency_ms = round((time.perf_counter() - t0) * 1000)
    call_log.append({"event": "turn_served", "path": "modular", "latency_ms": latency_ms})
    return {"reply": reply, "path": "modular", "audio_path": None, "latency_ms": latency_ms}


# ---------------------------------------------------------------------
# Compliance gate — disclosure/consent/erasure, extended below.
# ---------------------------------------------------------------------

def redact_image_ref(image_bytes: bytes) -> dict:
    """
    TODO 2: Never log raw image bytes. Return a dict with "sha256_16"
    (first 16 hex chars of hashlib.sha256(image_bytes).hexdigest()) and
    "size_bytes" (len(image_bytes)) — enough to prove an image was
    received without retaining the customer's actual photo in the log.
    """
    return {"sha256_16": hashlib.sha256(image_bytes).hexdigest()[:16], "size_bytes": len(image_bytes)}


def disclose_ai(call_log: list):
    call_log.append({"event": "disclosure_given", "text": DISCLOSURE_TEXT})


def request_recording_consent(call_log: list):
    call_log.append({"event": "consent_requested"})


def record_consent_response(call_log: list, response_text: str) -> bool:
    lowered = response_text.lower()
    granted = not any(marker in lowered for marker in CONSENT_REFUSAL_MARKERS)
    call_log.append({"event": "recording_consent", "granted": granted})
    return granted


def check_erasure_request(transcript: str) -> bool:
    """
    TODO 3: Return True if any string in ERASURE_KEYWORDS appears as a
    substring of transcript.lower().
    """
    lowered = transcript.lower()
    return any(keyword in lowered for keyword in ERASURE_KEYWORDS)


def log_agent_turn(call_log: list, reply: str, path: str, agent_initiated: bool = False):
    call_log.append({"event": "agent_turn", "reply": reply, "path": path, "agent_initiated": agent_initiated})


def handle_customer_turn(call_log: list, transcript: str, image_bytes: bytes | None = None) -> str:
    """
    TODO 4: If check_erasure_request(transcript), append {"event":
    "erasure_requested", "transcript": "[REDACTED]"} and return a fixed
    acknowledgement string — do NOT call run_resilient_turn for an erasure
    request. Otherwise: append a {"event": "customer_turn", "transcript":
    transcript} entry (with an "image" key from redact_image_ref() if
    image_bytes was given), call run_resilient_turn(), log_agent_turn()
    with the result, and return the reply.
    """
    if check_erasure_request(transcript):
        call_log.append({"event": "erasure_requested", "transcript": "[REDACTED]"})
        return "Understood — I won't reference anything from this call going forward, and I've flagged it for data erasure."

    entry = {"event": "customer_turn", "transcript": transcript}
    if image_bytes:
        entry["image"] = redact_image_ref(image_bytes)
    call_log.append(entry)

    result = run_resilient_turn(transcript, call_log)
    log_agent_turn(call_log, result["reply"], result["path"])
    return result["reply"]


# ---------------------------------------------------------------------
# Barge-in — InterruptionManager cancels playback immediately on VAD.
# ---------------------------------------------------------------------

async def simulate_tts_playback(text: str, chunk_delay: float = 0.15):
    words = text.split()
    for w in words:
        print(f"    [TTS playing]: {w}")
        await asyncio.sleep(chunk_delay)
    return "completed"


class InterruptionManager:
    def __init__(self):
        self.current_task = None
        self.is_speaking = False

    def start_speaking(self, task):
        self.current_task = task
        self.is_speaking = True

    def barge_in(self) -> bool:
        if self.is_speaking and self.current_task and not self.current_task.done():
            self.current_task.cancel()
            self.is_speaking = False
            return True
        return False


async def demo_barge_in(call_log: list):
    """
    TODO 5: Create an InterruptionManager. Start simulate_tts_playback() on
    a multi-word reply as an asyncio.Task, register it via
    start_speaking(). await asyncio.sleep(0.5), then call barge_in() and
    log {"event": "barge_in", "cancelled": <result>} to call_log. Await the
    task inside try/except asyncio.CancelledError, printing [CONFIRMED] if
    cancelled or a [WARNING] if it completed anyway.
    """
    mgr = InterruptionManager()
    reply = "I understand this has been a difficult claim, let me pull up the full history for you now"
    task = asyncio.create_task(simulate_tts_playback(reply))
    mgr.start_speaking(task)

    await asyncio.sleep(0.5)
    print("    [VAD] customer speech detected mid-playback -> barge_in()")
    cancelled = mgr.barge_in()
    call_log.append({"event": "barge_in", "cancelled": cancelled})

    try:
        await task
        print("    [WARNING] playback completed anyway")
    except asyncio.CancelledError:
        print("    [CONFIRMED] playback stopped immediately")


# ---------------------------------------------------------------------
# Call summary — aggregates the log into one reliability + compliance
# report, built entirely from events already written above.
# ---------------------------------------------------------------------

def summarize_call(call_log: list) -> dict:
    """
    TODO 6: Build the closing report from call_log, without adding any new
    events — everything needed is already in there:
      - served = the entries with event == "turn_served"
      - path_split: count of served entries per "path" value
      - avg_latency_ms / max_latency_ms: computed from each entry's
        "latency_ms", grouped by "path" (None if a path has zero entries)
      - native_failures: count of entries with event == "native_failed"
      - disclosure_given: True if any entry has event == "disclosure_given"
      - recording_consent_granted: the "granted" value of the entry with
        event == "recording_consent" (None if that event never happened)
      - erasure_requested: True if any entry has event == "erasure_requested"
      - barge_in_occurred: True if any entry has event == "barge_in" AND
        that entry's "cancelled" is truthy
    Return all of the above as one dict.
    """
    served = [e for e in call_log if e["event"] == "turn_served"]
    by_path = {"native": [], "modular": []}
    for e in served:
        by_path[e["path"]].append(e["latency_ms"])

    def _avg(latencies):
        return round(sum(latencies) / len(latencies)) if latencies else None

    consent_entry = next((e for e in call_log if e["event"] == "recording_consent"), None)

    return {
        "turns_served": len(served),
        "path_split": {path: len(latencies) for path, latencies in by_path.items()},
        "avg_latency_ms": {path: _avg(latencies) for path, latencies in by_path.items()},
        "max_latency_ms": {path: (max(latencies) if latencies else None) for path, latencies in by_path.items()},
        "native_failures": sum(1 for e in call_log if e["event"] == "native_failed"),
        "disclosure_given": any(e["event"] == "disclosure_given" for e in call_log),
        "recording_consent_granted": consent_entry["granted"] if consent_entry else None,
        "erasure_requested": any(e["event"] == "erasure_requested" for e in call_log),
        "barge_in_occurred": any(e["event"] == "barge_in" and e.get("cancelled") for e in call_log),
    }


if __name__ == "__main__":
    call_log = []

    disclose_ai(call_log)
    request_recording_consent(call_log)
    granted = record_consent_response(call_log, "Sure, that's fine.")
    print(f"Recording consent granted: {granted}")

    print("\n" + handle_customer_turn(call_log, "Can you check the status of my claim CLM-3391?"))
    print("\n" + handle_customer_turn(call_log, "Here's a photo of the damage.", image_bytes=b"fake-jpeg-bytes-for-demo"))

    proactive_reply = "I noticed it's been a moment — are you still there? Take your time."
    log_agent_turn(call_log, proactive_reply, path="native" if genai_client else "modular", agent_initiated=True)
    print(f"\nAgent (unprompted): {proactive_reply}")

    print("\n" + handle_customer_turn(call_log, "Actually, please delete my data from this call."))

    print("\n=== Barge-in ===")
    asyncio.run(demo_barge_in(call_log))

    print("\n--- call log ---")
    for entry in call_log:
        print(f"  {entry}")

    print("\n--- call summary ---")
    for key, value in summarize_call(call_log).items():
        print(f"  {key}: {value}")
