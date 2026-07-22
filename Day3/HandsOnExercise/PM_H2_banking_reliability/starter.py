"""
PM · H2 — Banking STT Primary + Fallback Resilience (STARTER)
No API key needed for the core exercise.
"""

import time
import random

PRIMARY_LATENCY_RANGE_MS = (120, 220)
FALLBACK_LATENCY_RANGE_MS = (200, 350)


class STTFailure(Exception):
    pass


def primary_stt(utterance: str, fail_rate: float = 0.3) -> str:
    """
    TODO 1: With probability `fail_rate`, raise STTFailure("primary down").
    Otherwise sleep a realistic latency (PRIMARY_LATENCY_RANGE_MS) and
    return `utterance` unchanged (pretend it was transcribed correctly).
    """
    raise NotImplementedError


def fallback_stt(utterance: str, fail_rate: float = 0.05) -> str:
    """
    TODO 2: Same shape as primary_stt, but with FALLBACK_LATENCY_RANGE_MS
    and the given (lower) fail_rate.
    """
    raise NotImplementedError


def robust_stt(utterance: str):
    """
    TODO 3: Try primary_stt(utterance). On STTFailure, try
    fallback_stt(utterance). If fallback ALSO raises STTFailure, return
    None. Otherwise return (transcript, which_provider) where
    which_provider is "primary" or "fallback".
    """
    raise NotImplementedError


def run_turn(utterance: str):
    """
    TODO 4: Call robust_stt(). If it returns None, print a graceful
    degradation message instead of the transcript. Otherwise print which
    provider served the request. Return which_provider or "degraded".
    """
    raise NotImplementedError


def prove_resilience(n_turns: int = 30):
    """
    TODO 5: Run run_turn() n_turns times with a sample utterance, tally
    outcomes ("primary", "fallback", "degraded"), and print the summary.
    Then compute and print what the degraded count WOULD have been with
    no fallback at all (i.e., just how many of n_turns primary_stt alone
    would statistically fail, at its raw fail_rate) for comparison.
    """
    raise NotImplementedError


if __name__ == "__main__":
    prove_resilience(30)
