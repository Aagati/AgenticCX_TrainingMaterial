"""
PM · H2 — Banking STT Primary + Fallback Resilience (REFERENCE SOLUTION)
"""

import time
import random

PRIMARY_LATENCY_RANGE_MS = (120, 220)
FALLBACK_LATENCY_RANGE_MS = (200, 350)
PRIMARY_FAIL_RATE = 0.3
FALLBACK_FAIL_RATE = 0.05


class STTFailure(Exception):
    pass


def primary_stt(utterance: str, fail_rate: float = PRIMARY_FAIL_RATE) -> str:
    if random.random() < fail_rate:
        raise STTFailure("primary provider unavailable")
    time.sleep(random.uniform(*PRIMARY_LATENCY_RANGE_MS) / 1000)
    return utterance


def fallback_stt(utterance: str, fail_rate: float = FALLBACK_FAIL_RATE) -> str:
    if random.random() < fail_rate:
        raise STTFailure("fallback provider unavailable")
    time.sleep(random.uniform(*FALLBACK_LATENCY_RANGE_MS) / 1000)
    return utterance


def robust_stt(utterance: str):
    try:
        return primary_stt(utterance), "primary"
    except STTFailure:
        try:
            return fallback_stt(utterance), "fallback"
        except STTFailure:
            return None


def run_turn(utterance: str):
    result = robust_stt(utterance)
    if result is None:
        print("  Agent: \"Sorry, I'm having trouble hearing you — could you try again in a moment?\"")
        return "degraded"
    transcript, provider = result
    print(f"  [{provider}] heard: \"{transcript}\"")
    return provider


def prove_resilience(n_turns: int = 30):
    sample_utterance = "What's my account balance?"
    outcomes = {"primary": 0, "fallback": 0, "degraded": 0}
    for _ in range(n_turns):
        outcome = run_turn(sample_utterance)
        outcomes[outcome] += 1

    print(f"\n=== Resilience summary over {n_turns} turns ===")
    for k, v in outcomes.items():
        print(f"  {k}: {v} ({v / n_turns * 100:.0f}%)")

    expected_no_fallback_failures = round(n_turns * PRIMARY_FAIL_RATE)
    print(f"\nWithout a fallback, ~{expected_no_fallback_failures} of {n_turns} turns "
          f"(the raw {PRIMARY_FAIL_RATE:.0%} primary fail rate) would have gone dead "
          f"instead of the {outcomes['degraded']} that actually did.")


if __name__ == "__main__":
    prove_resilience(30)

# Expected: roughly 70% served by primary, ~28% by fallback, ~1-2%
# genuinely degraded (both fail) — vs. ~30% degraded with no fallback at all.
