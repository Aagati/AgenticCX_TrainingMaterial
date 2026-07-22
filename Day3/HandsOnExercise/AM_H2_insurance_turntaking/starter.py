"""
AM · H2 — Insurance Turn-Taking / Endpointing Tuning (STARTER)
No API key needed — pure control-flow logic over provided test data.
"""

import json

with open("test_calls.json") as f:
    TEST_CALLS = json.load(f)

FILLER_ENDINGS = ("um", "uh", "so", "and", "on", "the", "to", "for", "of")


def is_turn_complete(silence_ms: int, threshold_ms: int) -> bool:
    """TODO 1: Return True once silence_ms >= threshold_ms."""
    raise NotImplementedError


def evaluate_threshold(threshold_ms: int):
    """
    TODO 2: For each call in TEST_CALLS, determine whether the agent WOULD
    interrupt (is_turn_complete(call["silence_ms"], threshold_ms) is True
    while call["is_real_end_of_turn"] is False -> that's a false
    interruption). Count false interruptions. Also compute the average
    "response delay" as: for calls that ARE real end-of-turn, how much
    silence the agent waited before responding — for a fixed threshold,
    that's just threshold_ms itself for every correctly-detected turn, so
    average delay = threshold_ms (this becomes more interesting in TODO 4).
    Return (false_interruption_count, avg_delay_ms).
    """
    raise NotImplementedError


def sweep_thresholds():
    """
    TODO 3: For threshold_ms in range(200, 1001, 100), call
    evaluate_threshold() and print a row: threshold, false interruptions,
    avg delay.
    """
    raise NotImplementedError


def ends_with_filler(transcript_so_far: str) -> bool:
    last_word = transcript_so_far.strip().split()[-1].lower().strip(".,!?")
    return last_word in FILLER_ENDINGS


def is_turn_complete_smart(transcript_so_far: str, silence_ms: int) -> bool:
    """
    TODO 4: If the transcript ends on a filler word (use ends_with_filler),
    require a LONGER threshold (e.g. 700ms) before considering the turn
    complete. Otherwise, use a SHORTER threshold (e.g. 350ms). Return
    whether silence_ms meets the applicable threshold.
    """
    raise NotImplementedError


def evaluate_smart():
    """
    TODO 5: Like evaluate_threshold, but using is_turn_complete_smart
    instead of a fixed threshold. Print the false interruption count and
    compare it to the best fixed-threshold result from the sweep.
    """
    raise NotImplementedError


if __name__ == "__main__":
    print("=== Fixed threshold sweep ===")
    sweep_thresholds()

    print("\n=== Smart (filler-aware) endpointing ===")
    evaluate_smart()


# ============================================================
# Part 2 — Barge-in (required)
# ============================================================
import asyncio


async def simulate_tts_playback(text: str, chunk_delay: float = 0.15):
    """
    TODO 6: Split `text` into words. For each word, print
    f"  [TTS playing]: {word}" and `await asyncio.sleep(chunk_delay)`.
    Return "completed" after all words are done.
    """
    raise NotImplementedError


class InterruptionManager:
    """
    TODO 7: __init__ should set self.current_task = None and
    self.is_speaking = False.

    start_speaking(self, task): store `task` as self.current_task and set
    self.is_speaking = True.

    barge_in(self) -> bool: if self.is_speaking is True AND
    self.current_task is not None AND not self.current_task.done(), call
    self.current_task.cancel(), set self.is_speaking = False, and return
    True. Otherwise return False.
    """
    def __init__(self):
        raise NotImplementedError

    def start_speaking(self, task):
        raise NotImplementedError

    def barge_in(self) -> bool:
        raise NotImplementedError


async def demo_barge_in():
    """
    TODO 8: Create an InterruptionManager. Start simulate_tts_playback()
    on some multi-word reply as an asyncio.Task (asyncio.create_task),
    register it via start_speaking(). await asyncio.sleep(0.5) to simulate
    the customer starting to talk partway through. Call barge_in() and
    print whether it triggered. Then await the task inside a try/except
    asyncio.CancelledError — print [CONFIRMED] if cancelled, or a warning
    if it completed anyway.
    """
    raise NotImplementedError


if __name__ == "__main__":
    print("\n\n=== Part 2: Barge-in ===")
    asyncio.run(demo_barge_in())
