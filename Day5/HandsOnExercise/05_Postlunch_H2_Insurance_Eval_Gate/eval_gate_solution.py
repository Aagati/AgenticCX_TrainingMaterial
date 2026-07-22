"""
Day 5 · Post-Lunch Lab H2 (Insurance) — Eval-Gated Rollout
============================================================
FACILITATOR REFERENCE SOLUTION.

Expected verdicts against the provided data:
  v2.1-candidate -> PASS      (resolution improves, zero safety violations)
  v2.2-candidate -> BLOCKED   (resolution regression: 60% < 80% baseline)
  v2.3-candidate -> BLOCKED   (2 safety violations, despite 100% resolution)
"""

import json


def load_data(path="candidate_versions.json"):
    with open(path) as f:
        return json.load(f)


def resolution_rate(results: list) -> float:
    resolved = sum(1 for r in results if r["resolved"])
    return resolved / len(results)


def safety_violation_count(results: list) -> int:
    return sum(1 for r in results if r.get("safety_violation"))


def evaluate_gate(baseline_resolution_rate: float, candidate: dict) -> dict:
    results = candidate["results"]
    cand_rate = resolution_rate(results)
    violations = safety_violation_count(results)

    reasons = []
    if cand_rate < baseline_resolution_rate:
        reasons.append(
            f"Resolution regression: {cand_rate:.0%} vs. baseline {baseline_resolution_rate:.0%}."
        )
    if violations > 0:
        reasons.append(
            f"{violations} safety violation(s) detected — zero tolerance, no manual override."
        )

    verdict = "BLOCKED" if reasons else "PASS"
    return {
        "version": candidate["version"],
        "verdict": verdict,
        "reasons": reasons or ["Meets or beats baseline resolution; zero safety violations."],
        "resolution_rate": cand_rate,
        "safety_violations": violations,
    }


def run_gate_report(path="candidate_versions.json"):
    data = load_data(path)
    baseline_rate = data["baseline"]["resolution_rate"]

    print(f"Baseline (production) resolution rate: {baseline_rate:.0%}\n")

    for candidate in data["candidates"]:
        verdict = evaluate_gate(baseline_rate, candidate)
        status_symbol = "✅" if verdict["verdict"] == "PASS" else "⛔"
        print(f"{status_symbol} {verdict['version']}: {verdict['verdict']} "
              f"(resolution {verdict['resolution_rate']:.0%}, "
              f"{verdict['safety_violations']} safety violation(s))")
        for reason in verdict["reasons"]:
            print(f"    - {reason}")
        print()


if __name__ == "__main__":
    run_gate_report()
