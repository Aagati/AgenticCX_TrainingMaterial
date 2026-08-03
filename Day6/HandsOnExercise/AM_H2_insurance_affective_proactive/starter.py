"""
AM · H2 — Insurance: Affective Dialogue & Proactive Audio (STARTER)

Both Gemini Live features try REAL calls first (TODOs below) and fall back
to a deterministic simulated rule if GEMINI_API_KEY isn't set, the SDK
isn't installed, or the call fails at runtime — so this lab runs for every
student, key or no key.
"""

import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "call_transcripts.json") as f:
    TEST_CALLS = json.load(f)

# Current native-audio-dialog model id as of this writing — check
# ai.google.dev/gemini-api/docs/models for a newer one before class.
NATIVE_AUDIO_MODEL = "gemini-live-2.5-flash-native-audio"

SYSTEM_PROMPT = (
    "You are an insurance claims check-in agent calling a policyholder "
    "about an open claim. Adapt your tone to how the caller sounds — "
    "reassuring and unhurried if they sound distressed, brisk and "
    "efficient if they sound fine. Reply in short spoken sentences."
)

DISTRESS_WORDS = {
    "frustrated", "angry", "upset", "worried", "stressed",
    "furious", "scared", "anxious", "fed up", "nightmare",
}
POSITIVE_WORDS = {"thanks", "thank", "great", "appreciate", "perfect"}

PROACTIVE_TIMEOUT_S = 6.0

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _vertex_client import get_genai_client, save_pcm_wav

AUDIO_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_audio_out")

genai_client, genai_types = get_genai_client(location="us-central1")
if genai_client is None:
    print("No working Gemini credentials — both paths will use simulation.")


def detect_affect_cues(transcript: str) -> str:
    """
    TODO 1: Text-only stand-in for what a native-audio model hears directly
    in tone/prosody. Return "distressed" if the transcript contains any
    DISTRESS_WORDS, has 2+ "!" characters, or has any all-caps word longer
    than 2 characters. Otherwise return "positive" if it contains any
    POSITIVE_WORDS. Otherwise return "neutral".
    """
    lowered = transcript.lower()
    exclaim = transcript.count("!")
    caps_words = sum(1 for w in transcript.split() if w.isupper() and len(w) > 2)
    distress_hits = sum(1 for w in DISTRESS_WORDS if w in lowered)

    if distress_hits > 0 or exclaim >= 2 or caps_words >= 1:
        return "distressed"
    if any(w in lowered for w in POSITIVE_WORDS):
        return "positive"
    return "neutral"


def evaluate_affect_detection():
    """
    TODO 2: For each call in TEST_CALLS, run detect_affect_cues() and
    compare to call["expected_affect"]. Print a per-call OK/MISS line and a
    final "N/total correct" summary.
    """
    correct = 0
    for call in TEST_CALLS:
        predicted = detect_affect_cues(call["transcript"])
        hit = predicted == call["expected_affect"]
        correct += hit
        status = "OK" if hit else "MISS"
        print(f"  {call['call_id']}: predicted={predicted:<11} expected={call['expected_affect']:<11} [{status}]")
    print(f"\n{correct}/{len(TEST_CALLS)} correct")


def build_live_config(enable_affect: bool, enable_proactive: bool):
    """
    TODO 3: Build a genai_types.LiveConnectConfig. Always set
    response_modalities=["AUDIO"] and system_instruction=SYSTEM_PROMPT. If
    enable_affect, also set enable_affective_dialog=True. If
    enable_proactive, also set proactivity=genai_types.ProactivityConfig(
    proactive_audio=True).
    """
    kwargs = {"response_modalities": ["AUDIO"], "system_instruction": SYSTEM_PROMPT}
    if enable_affect:
        kwargs["enable_affective_dialog"] = True
    if enable_proactive:
        kwargs["proactivity"] = genai_types.ProactivityConfig(proactive_audio=True)
    return genai_types.LiveConnectConfig(**kwargs)


async def _run_affective_turn_async(user_utterance: str, enable_affect: bool) -> dict:
    """
    TODO 4: build_live_config(enable_affect, enable_proactive=False), open
    a Live session via genai_client.aio.live.connect(model=
    NATIVE_AUDIO_MODEL, config=config), send the turn with
    session.send_client_content(turns={"parts": [{"text": user_utterance}]},
    turn_complete=True), then iterate session.receive() collecting any
    server_content.model_turn.parts[].text until turn_complete. Return the
    joined text (or a placeholder string if no text parts arrived).
    """
    config = build_live_config(enable_affect=enable_affect, enable_proactive=False)
    reply_text = []
    audio_bytes = bytearray()
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
                    if part.text:
                        reply_text.append(part.text)
                    if part.inline_data and part.inline_data.data:
                        audio_bytes.extend(part.inline_data.data)
            if sc.turn_complete:
                break
    audio_path = None
    if audio_bytes:
        fname = f"affect_{'on' if enable_affect else 'off'}_{int(time.time() * 1000)}.wav"
        audio_path = save_pcm_wav(bytes(audio_bytes), os.path.join(AUDIO_OUT_DIR, fname))
    return {
        "text": "".join(reply_text) or "(audio-only reply — model didn't return a text part)",
        "audio_path": audio_path,
    }


def run_affective_turn(user_utterance: str, enable_affect: bool) -> dict:
    """Given — dispatches to the real async call when Gemini is
    configured; falls back to a rule keyed on detect_affect_cues()
    otherwise."""
    if genai_client is not None:
        try:
            result = asyncio.run(_run_affective_turn_async(user_utterance, enable_affect))
            return {"reply": result["text"], "audio_path": result["audio_path"], "real": True}
        except Exception as exc:
            print(f"Gemini Live call failed ({exc}) — falling back to simulated reply.")

    affect = detect_affect_cues(user_utterance)
    if enable_affect and affect == "distressed":
        reply = "I hear that this has been stressful — take your time, I'm not in a rush. Let's go through your claim together."
    elif enable_affect and affect == "positive":
        reply = "Great, glad to hear it! Let's knock this out quickly."
    else:
        reply = "I'm calling about your open claim. Can you confirm a few details?"
    return {"reply": reply, "audio_path": None, "real": False}


def compare_affect_modes(user_utterance: str):
    """
    TODO 5: Call run_affective_turn() with enable_affect=False and then
    True for the same utterance. Print both replies labeled with whether
    each came from a real call or simulation.
    """
    print(f'\n--- "{user_utterance}" ---')
    off = run_affective_turn(user_utterance, enable_affect=False)
    on = run_affective_turn(user_utterance, enable_affect=True)
    print(f"  affect OFF ({'real' if off['real'] else 'sim'}): {off['reply']}")
    if off.get("audio_path"):
        print(f"    audio saved: {off['audio_path']}")
    print(f"  affect ON  ({'real' if on['real'] else 'sim'}): {on['reply']}")
    if on.get("audio_path"):
        print(f"    audio saved: {on['audio_path']}")


async def _listen_for_proactive_async(opening_utterance: str) -> bool:
    """
    TODO 6: build_live_config(enable_affect=True, enable_proactive=True),
    open a session, send opening_utterance as a turn, drain the direct
    reply (loop session.receive() until server_content.turn_complete).
    THEN, with no further client input, wrap another session.receive()
    loop in `async with asyncio.timeout(PROACTIVE_TIMEOUT_S):` and return
    True the moment ANY message with server_content arrives unprompted.
    Catch TimeoutError and return False if nothing arrives in time.
    """
    config = build_live_config(enable_affect=True, enable_proactive=True)
    async with genai_client.aio.live.connect(model=NATIVE_AUDIO_MODEL, config=config) as session:
        await session.send_client_content(
            turns={"parts": [{"text": opening_utterance}]}, turn_complete=True,
        )
        async for message in session.receive():
            if message.server_content and message.server_content.turn_complete:
                break
        try:
            async with asyncio.timeout(PROACTIVE_TIMEOUT_S):
                async for message in session.receive():
                    if message.server_content:
                        return True
        except TimeoutError:
            pass
    return False


def listen_for_proactive_checkin(opening_utterance: str, caller_affect: str) -> dict:
    """
    TODO 7: Dispatch to _listen_for_proactive_async() when Gemini is
    configured. Otherwise, simulate: return True with probability 0.7 if
    caller_affect == "distressed", else probability 0.15 (models the idea
    that a distressed caller is more likely to get an unprompted check-in
    during a silence gap).
    """
    if genai_client is not None:
        try:
            return {"proactive": asyncio.run(_listen_for_proactive_async(opening_utterance)), "real": True}
        except Exception as exc:
            print(f"Gemini Live call failed ({exc}) — falling back to simulated proactivity rule.")

    probability = 0.7 if caller_affect == "distressed" else 0.15
    return {"proactive": random.random() < probability, "real": False}


if __name__ == "__main__":
    print("=== Affect detection accuracy ===")
    evaluate_affect_detection()

    print("\n=== Affective dialogue on/off ===")
    for call in TEST_CALLS[:3]:
        compare_affect_modes(call["transcript"])

    print("\n=== Proactive audio check-in ===")
    for call in TEST_CALLS[:3]:
        affect = detect_affect_cues(call["transcript"])
        result = listen_for_proactive_checkin(call["transcript"], affect)
        source = "real" if result["real"] else "simulated"
        print(f"  {call['call_id']} ({affect}, {source}): proactive check-in = {result['proactive']}")
