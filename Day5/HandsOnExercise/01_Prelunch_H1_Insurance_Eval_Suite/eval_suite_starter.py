"""
Day 5 · Pre-Lunch Lab H1 (Insurance) — Resolution + Trajectory Eval Suite
==========================================================================

OBJECTIVE
---------
Build an evaluation suite that scores each golden conversation on two
independent lenses:

  1. RESOLUTION  — did the conversation actually solve the customer's
     problem? (outcome)
  2. TRAJECTORY  — did the agent take the right steps, in the right
     order, following policy? (process)

You do NOT need an LLM or any API key for this lab. Everything you need
is already in goldens.json: each record has the agent's actual actions
(`agent_actions`) and the correct actions per policy (`expected_actions`),
plus a ground-truth resolution flag (`expected_resolution`).

Fill in the three TODOs below, then run:
    python eval_suite_starter.py

WHAT "DONE" LOOKS LIKE
-----------------------
A printed report with one row per golden conversation showing:
  - resolution score (0 or 1)
  - trajectory score (0.0 - 1.0)
  - a combined score
  - a flag for any conversation that scores below 0.6 combined,
    with a one-line reason a human reviewer should look at it

STRETCH GOAL (optional)
------------------------
Extend trajectory_score so a *redundant but harmless* extra tool call
(see G04 in the data) is penalised less than a *missing required* tool
call or an *out-of-order* one (see G02, G08).
"""

import json


def load_goldens(path="goldens.json"):
    with open(path) as f:
        data = json.load(f)
    return data["goldens"]


def resolution_score(conversation: dict) -> int:
    """
    TODO 1 — Resolution scorer.

    Return 1 if the conversation resolved the customer's problem,
    0 otherwise.

    Hint: the ground truth is already provided in the data as
    conversation["expected_resolution"] (True/False). In a real eval
    suite this label usually comes from human review or an LLM-as-judge
    reading the transcript — here it's given to you so you can focus on
    building the scoring *pipeline* rather than the judge itself.
    """
    # YOUR CODE HERE
    raise NotImplementedError


def trajectory_score(conversation: dict) -> float:
    """
    TODO 2 — Trajectory scorer.

    Compare conversation["agent_actions"] (what actually happened)
    against conversation["expected_actions"] (what should have
    happened) and return a score between 0.0 and 1.0.

    A simple, defensible approach:
      - 1.0 if agent_actions == expected_actions exactly
      - 0.0 if any *required* action is missing, or the actions that
        ARE present are in the wrong order
      - Something in between (e.g. 0.85) if the agent did everything
        required, correctly ordered, but added extra/redundant calls

    There's no single "correct" formula here — document whatever rule
    you choose so a teammate could apply it consistently.
    """
    # YOUR CODE HERE
    raise NotImplementedError


def combined_score(res_score: int, traj_score: float) -> float:
    """
    TODO 3 — Combine the two lenses into one number for triage.

    Suggested starting weights: 60% resolution, 40% trajectory — but
    feel free to justify a different split (e.g. should a resolved
    conversation that broke policy still score highly?).
    """
    # YOUR CODE HERE
    raise NotImplementedError


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


if __name__ == "__main__":
    run_report()
