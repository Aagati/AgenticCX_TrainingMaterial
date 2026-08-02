# -*- coding: utf-8 -*-
"""
BONUS TIER B - Voice Channel (real Deepgram only - no simulated fallback)

There is NO solution file for this part. If you attempt it, it must use
the REAL Deepgram API - per the brief, a simulated STT/TTS path defeats
the point of this bonus, which is proving Day2's "channel-agnostic core"
claim with an ACTUAL different input modality, not just asserting it.

What this reuses, rather than reinventing:
  - The real Deepgram Nova-3 STT / Aura TTS calling convention from
    Day3/HandsOnExercise/AM_H1_banking_latency/solution.py (real_stt(),
    real_tts_stream(), open_tts_stream() - same deepgram-sdk==7.5.0 API
    already pinned in the repo root's requirements-voice.txt).
  - The AI-disclosure + recording-consent gate from
    Day3/HandsOnExercise/PM_H3_telecom_compliance/solution.py
    (disclose_ai() / request_recording_consent()) - TEL-POL-02 in this
    capstone's own knowledge base requires exactly this before any
    account-specific discussion begins, and RT-06 in the red-team tier
    is a live attack on skipping it.
  - agent_team.run_turn() COMPLETELY UNMODIFIED - the deliverable is
    that Deepgram's transcribed text becomes the user_message into the
    SAME function every other channel uses. If you find yourself
    editing run_turn() to make voice work, that's a sign the "channel-
    agnostic core" design has a leak worth discussing, not a green light
    to patch around it here.

Setup (only if you're attempting this):
    pip install -r ../requirements.txt          (already has deepgram-sdk)
    pip install -r ../../requirements-voice.txt  (installs SECOND - see
        that file's own header comment on why order matters: it pins
        json-repair 0.60.1, which conflicts with crewai's 0.25.x pin if
        resolved in one pip invocation)
    Set DEEPGRAM_API_KEY in the repo-root .env.
    Record 1-2 short (<10s) mono WAV files into a sample_audio/ folder
    next to this script (see the Day3 lab's own instructions for how).

Run: python voice_channel_bonus.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

_STARTER_DIR = Path(__file__).resolve().parent.parent / "starter"
if _STARTER_DIR.exists() and str(_STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(_STARTER_DIR))

AUDIO_DIR = Path(__file__).parent / "sample_audio"

deepgram = None
if os.environ.get("DEEPGRAM_API_KEY"):
    try:
        from deepgram import DeepgramClient
        deepgram = DeepgramClient(api_key=os.environ["DEEPGRAM_API_KEY"])
    except Exception as exc:  # noqa: BLE001
        print(f"Deepgram setup failed ({exc}) - this bonus needs a real key to run at all.")
        deepgram = None


def real_stt(audio_path: Path) -> str:
    """Real Deepgram Nova-3 prerecorded transcription - same call shape
    as Day3 AM_H1_banking_latency's real_stt(). TODO if you're attempting
    this bonus: wire in whatever STT model/options you want; this is
    given as a starting point, not a locked interface."""
    with open(audio_path, "rb") as f:
        response = deepgram.listen.v1.media.transcribe_file(
            request=f.read(), model="nova-3-general", smart_format=True,
        )
    return response.results.channels[0].alternatives[0].transcript


def disclose_ai(call_log: list) -> None:
    """Given (same shape as Day3 PM_H3_telecom_compliance's
    disclose_ai()) - TEL-POL-02 requires this before any account-
    specific discussion begins."""
    print('Agent: "Before we continue - you\'re speaking with an AI assistant, not a human agent."')
    call_log.append({"event": "disclosure_given"})


def request_recording_consent(call_log: list, caller_response: str) -> bool:
    """Given (same shape as Day3 PM_H3_telecom_compliance) - returns
    whether consent was granted; the call should not proceed to
    account-specific discussion if this is False without further
    escalation (an exercise left to you)."""
    print('Agent: "This call may be recorded for quality purposes. Is that okay with you?"')
    granted = "no" not in caller_response.lower() and "don't" not in caller_response.lower()
    call_log.append({"event": "recording_consent", "granted": granted})
    print(f"  Caller: \"{caller_response}\" -> Recording: {'ON' if granted else 'OFF'}")
    return granted


# TODO (open-ended, no solution): wire the pieces above into a working
# call.
#
#   1. Run disclose_ai(call_log), then request_recording_consent().
#      Refuse to proceed to Step 2 if consent is refused - decide for
#      yourself what "refuse" means here (end the call? continue
#      unrecorded but disclosed? your call, document your reasoning).
#   2. For each turn: real_stt(audio_path) -> transcript.
#   3. Feed that transcript into agent_team.run_turn(transcript, ctx)
#      UNCHANGED - import new_session/run_turn from agent_team (already
#      on sys.path via the starter/ insert above) exactly as
#      agent_team.main() does, including spawning mcp_server.py via
#      StdioServerParameters/stdio_client/ClientSession.
#   4. Synthesize the reply with real Deepgram Aura TTS - see Day3
#      AM_H1_banking_latency's real_tts_stream()/open_tts_stream() for
#      the exact websocket-reuse pattern (one connection per call, not
#      one per turn - a fresh handshake costs ~1.3-1.6s on its own).
#   5. Extra credit: gate apply_billing_credit / change_plan /
#      create_service_ticket on a SPOKEN confirmation, not just a
#      transcribed "yes" - what's different about verifying spoken
#      consent versus a typed one?
#
# Discussion questions (bring back to the group, whether or not you
# have real hardware/audio to test with):
#   - What in agent_team.py had to change to support this channel? (The
#     answer should be "nothing" - if it's not, why not?)
#   - RT-06's compliance-suppression attack tries to skip disclosure for
#     "returning customers." If a customer says "you already told me
#     that last time," what should happen?
#   - The written channel's output_guardrail() checks for a leaked
#     idempotency key or an unowned account number in TEXT. Does a
#     spoken reply need the same check, or does something about voice
#     change what "leaked" even means?


async def _demo_without_hardware():
    """Given: proves the pieces IMPORT and the disclosure/consent gate
    runs, without needing a real WAV file or a live call. This is NOT
    the bonus - it's a sanity check that your environment is wired up
    before you attempt the real thing."""
    call_log: list = []
    disclose_ai(call_log)
    granted = request_recording_consent(call_log, "yes that's fine")
    print(f"\ncall_log so far: {call_log}")
    print(f"Consent granted: {granted}")
    print(f"Deepgram client configured: {deepgram is not None}")
    if deepgram is None:
        print("\nSet DEEPGRAM_API_KEY in the repo-root .env to attempt the real bonus.")
    elif not AUDIO_DIR.exists():
        print(f"\nNo {AUDIO_DIR.name}/ folder found next to this script - add a WAV file to attempt real_stt().")


if __name__ == "__main__":
    asyncio.run(_demo_without_hardware())
