"""
AM · H2 — Insurance Turn-Taking / Endpointing Tuning (REFERENCE SOLUTION)
"""

import json

with open("test_calls.json") as f:
    TEST_CALLS = json.load(f)

FILLER_ENDINGS = ("um", "uh", "so", "and", "on", "the", "to", "for", "of")


def is_turn_complete(silence_ms: int, threshold_ms: int) -> bool:
    return silence_ms >= threshold_ms


def evaluate_threshold(threshold_ms: int):
    false_interruptions = 0
    delays = []
    for call in TEST_CALLS:
        would_end = is_turn_complete(call["silence_ms"], threshold_ms)
        if would_end and not call["is_real_end_of_turn"]:
            false_interruptions += 1
        if call["is_real_end_of_turn"] and would_end:
            delays.append(threshold_ms)
    avg_delay = sum(delays) / len(delays) if delays else 0
    return false_interruptions, avg_delay


def sweep_thresholds():
    print(f"{'Threshold':>10} | {'False Interruptions':>20} | {'Avg Delay (ms)':>15}")
    for threshold_ms in range(200, 1001, 100):
        fi, delay = evaluate_threshold(threshold_ms)
        print(f"{threshold_ms:>10} | {fi:>20} | {delay:>15.0f}")


def ends_with_filler(transcript_so_far: str) -> bool:
    last_word = transcript_so_far.strip().split()[-1].lower().strip(".,!?")
    return last_word in FILLER_ENDINGS


def is_turn_complete_smart(transcript_so_far: str, silence_ms: int) -> bool:
    threshold_ms = 700 if ends_with_filler(transcript_so_far) else 350
    return silence_ms >= threshold_ms


def evaluate_smart():
    false_interruptions = 0
    delays = []
    for call in TEST_CALLS:
        would_end = is_turn_complete_smart(call["transcript_so_far"], call["silence_ms"])
        if would_end and not call["is_real_end_of_turn"]:
            false_interruptions += 1
            print(f"  FALSE INTERRUPTION on {call['call_id']}: \"{call['transcript_so_far']}\" ({call['note']})")
        if call["is_real_end_of_turn"] and would_end:
            applicable = 700 if ends_with_filler(call["transcript_so_far"]) else 350
            delays.append(applicable)
    avg_delay = sum(delays) / len(delays) if delays else 0
    print(f"\nSmart endpointing: {false_interruptions} false interruptions, "
          f"{avg_delay:.0f}ms avg delay on correctly-detected turns.")


if __name__ == "__main__":
    print("=== Fixed threshold sweep ===")
    sweep_thresholds()

    print("\n=== Smart (filler-aware) endpointing ===")
    evaluate_smart()

# Expected: at threshold=450ms fixed, several false interruptions remain
# (calls 3, 5, 7 all have silence_ms >= 450 despite trailing off). The
# smart version catches those (their transcripts end on filler/trailing
# words) while keeping short delays on genuinely complete short replies
# like call_4, call_6, call_8.


# ============================================================
# Part 2 — Barge-in (required)
# ============================================================
import asyncio


async def simulate_tts_playback(text: str, chunk_delay: float = 0.15):
    words = text.split()
    for w in words:
        print(f"  [TTS playing]: {w}")
        await asyncio.sleep(chunk_delay)
    return "completed"


class InterruptionManager:
    def __init__(self):
        self.current_task = None
        self.is_speaking = False

    def start_speaking(self, task: asyncio.Task):
        self.current_task = task
        self.is_speaking = True

    def barge_in(self) -> bool:
        if self.is_speaking and self.current_task and not self.current_task.done():
            self.current_task.cancel()
            self.is_speaking = False
            return True
        return False


async def demo_barge_in():
    mgr = InterruptionManager()
    reply = "I can help you with that claim, let me pull up the details for your policy now"
    task = asyncio.create_task(simulate_tts_playback(reply))
    mgr.start_speaking(task)

    # Simulate the customer starting to talk 0.5s into playback.
    await asyncio.sleep(0.5)
    print("\n  [VAD] customer speech detected mid-playback -> barge_in()")
    cancelled = mgr.barge_in()
    print(f"  [RESULT] cancellation triggered: {cancelled}")

    try:
        await task
        print("  [WARNING] playback completed anyway — cancellation didn't take effect")
    except asyncio.CancelledError:
        print("  [CONFIRMED] playback stopped immediately, did not finish the sentence")


if __name__ == "__main__":
    print("\n\n=== Part 2: Barge-in ===")
    asyncio.run(demo_barge_in())

# Expected: playback prints roughly 3-4 words ("I can help you...") before
# being cut off at the 0.5s mark, then [CONFIRMED] prints — NOT all ~16
# words of the reply. If you see [WARNING], the cancellation isn't wired
# correctly (a common bug: cancelling the wrong task object, or catching
# CancelledError inside simulate_tts_playback and swallowing it).
