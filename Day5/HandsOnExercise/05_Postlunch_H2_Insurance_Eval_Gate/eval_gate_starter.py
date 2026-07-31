"""
Day 5 · Post-Lunch Lab H2 (Insurance) — Eval-Gated Rollout
============================================================

OBJECTIVE
---------
Wire an automated gate that blocks a candidate agent release if it:
  (a) regresses resolution rate below the current production baseline, or
  (b) has ANY safety/guardrail violation (zero tolerance).

Data: candidate_versions.json has a "baseline" (the current production
agent) and three "candidates" — one should pass your gate, two should
fail it for two different reasons. Your job is to build the gate, not
to pick the outcome; the data will tell you if your gate is right.

Fill in the TODOs, then run:
    python eval_gate_starter.py

WHAT "DONE" LOOKS LIKE
-----------------------
For each candidate, a printed verdict: PASS or BLOCKED, with a clear
reason when blocked. By the end you should be able to say, for each of
the three candidates in the data, exactly why your gate did what it did.

STRETCH GOAL (optional)
------------------------
Right now the resolution-rate comparison is a hard >= baseline check.
Add a small configurable tolerance (e.g. gate fails only if the drop is
more than 2 percentage points) and discuss with your table: what's the
risk of adding that tolerance?
"""

import json
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
CANDIDATES_PATH = os.path.join(LAB_DIR, "candidate_versions.json")


def load_data(path=CANDIDATES_PATH):
    with open(path) as f:
        return json.load(f)


def resolution_rate(results: list) -> float:
    """
    TODO 1 — Given a candidate's `results` list (each item has a
    "resolved" boolean), return the resolution rate as a float 0.0-1.0.
    """
    # YOUR CODE HERE
    raise NotImplementedError


def safety_violation_count(results: list) -> int:
    """
    TODO 2 — Count how many results have safety_violation == True.
    """
    # YOUR CODE HERE
    raise NotImplementedError


def evaluate_gate(baseline_resolution_rate: float, candidate: dict) -> dict:
    """
    TODO 3 — The gate itself.

    Return a dict like:
        {"version": ..., "verdict": "PASS" or "BLOCKED", "reasons": [...]}

    Gate rules:
      - BLOCKED if candidate resolution_rate < baseline_resolution_rate
        (append a reason string explaining the numbers)
      - BLOCKED if safety_violation_count > 0
        (append a reason string — zero tolerance, no override)
      - PASS only if neither condition triggers
      - A candidate can be BLOCKED for both reasons at once — include
        every reason that applies, don't stop at the first.
    """
    # YOUR CODE HERE
    raise NotImplementedError


def run_gate_report(path=CANDIDATES_PATH):
    data = load_data(path)
    baseline_rate = data["baseline"]["resolution_rate"]

    print(f"Baseline (production) resolution rate: {baseline_rate:.0%}\n")

    for candidate in data["candidates"]:
        verdict = evaluate_gate(baseline_rate, candidate)
        status_symbol = "✅" if verdict["verdict"] == "PASS" else "⛔"
        print(f"{status_symbol} {verdict['version']}: {verdict['verdict']}")
        for reason in verdict["reasons"]:
            print(f"    - {reason}")
        print()


if __name__ == "__main__":
    run_gate_report()
