"""
Day 5 · Pre-Lunch Lab H1 (Insurance) — Resolution + Trajectory Eval Suite
==========================================================================
FACILITATOR REFERENCE SOLUTION — one valid way to complete the lab.
Participants' scoring rules do not need to match this exactly; what
matters is that they can justify their weighting and their trajectory
comparison logic.
"""

import json


def load_goldens(path="goldens.json"):
    with open(path) as f:
        data = json.load(f)
    return data["goldens"]


def resolution_score(conversation: dict) -> int:
    return 1 if conversation["expected_resolution"] else 0


def trajectory_score(conversation: dict) -> float:
    actual = conversation["agent_actions"]
    expected = conversation["expected_actions"]

    # Perfect match
    if actual == expected:
        return 1.0

    # Missing a required action -> hard fail on trajectory
    missing = [a for a in expected if a not in actual]
    if missing:
        return 0.0

    # Out-of-order: required actions all present, but not in the
    # expected relative order -> hard fail (policy sequencing matters,
    # e.g. verify_identity must precede any disclosure).
    # De-duplicate first so a *repeated* required call (harmless) isn't
    # mistaken for an *out-of-order* one (a policy problem).
    actual_required_order = list(dict.fromkeys(a for a in actual if a in expected))
    if actual_required_order != expected:
        return 0.0

    # All required actions present and correctly ordered, but with
    # extra/redundant calls layered in -> partial credit
    extra_calls = len(actual) - len(expected)
    penalty = min(0.15 * extra_calls, 0.3)
    return round(1.0 - penalty, 2)


def combined_score(res_score: int, traj_score: float) -> float:
    return round(0.6 * res_score + 0.4 * traj_score, 2)


def run_report(goldens_path="goldens.json", flag_threshold=0.6):
    goldens = load_goldens(goldens_path)

    print(f"{'ID':<5}{'Intent':<22}{'Resolution':<12}{'Trajectory':<12}{'Combined':<10}Flag")
    print("-" * 80)

    flagged = []
    for g in goldens:
        r = resolution_score(g)
        t = trajectory_score(g)
        c = combined_score(r, t)
        flag = c < flag_threshold
        if flag:
            flagged.append((g["id"], g.get("policy_notes", "")))

        print(f"{g['id']:<5}{g['intent']:<22}{r:<12}{round(t,2):<12}{round(c,2):<10}{'⚑ REVIEW' if flag else ''}")

    print("\nFlagged for human review:")
    for gid, note in flagged:
        print(f"  - {gid}: {note}")

    # Suite-level summary, useful for the "SHIPS ->" artifact
    avg_resolution = sum(resolution_score(g) for g in goldens) / len(goldens)
    avg_trajectory = sum(trajectory_score(g) for g in goldens) / len(goldens)
    print(f"\nSuite summary: resolution rate = {avg_resolution:.0%}, "
          f"avg trajectory score = {avg_trajectory:.2f}")


if __name__ == "__main__":
    run_report()
