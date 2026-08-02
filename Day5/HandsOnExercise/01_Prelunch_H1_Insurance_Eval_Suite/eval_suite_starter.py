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

Fill in the three TODOs below. Everything you need for RESOLUTION and
TRAJECTORY is already in goldens.json: each record has the agent's actual
actions (`agent_actions`) and the correct actions per policy
(`expected_actions`), plus a ground-truth resolution flag
(`expected_resolution`) — no LLM call needed for those two scorers.

This lab also traces every golden through Langfuse and runs a real
LLM-as-judge pass over the agent's final reply (`llm_judge_score`,
already implemented below) — a check the static goldens fields can't do
on their own (tone, policy adherence in the actual wording). You don't
need to touch the judge or the tracing code; once your three TODOs are
filled in, `run_report()` wires everything together and each golden shows
up as a trace in the Langfuse UI with all four scores attached.

Setup:
    pip install langfuse anthropic pydantic python-dotenv
    Set ANTHROPIC_API_KEY and LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
    LANGFUSE_BASE_URL in .env at the repo root (cloud.langfuse.com has a
    free tier; placeholders should already be in .env).

Run:
    python eval_suite_starter.py

WHAT "DONE" LOOKS LIKE
-----------------------
A printed report with one row per golden conversation showing:
  - resolution score (0 or 1)
  - trajectory score (0.0 - 1.0)
  - a combined score
  - an LLM-judge score (1-5)
  - a flag for any conversation that scores below 0.6 combined OR <=2 on
    the judge, with a one-line reason a human reviewer should look at it
...plus one trace per golden in the Langfuse UI, each carrying all four
scores.

STRETCH GOAL (optional)
------------------------
Extend trajectory_score so a *redundant but harmless* extra tool call
(see G04 in the data) is penalised less than a *missing required* tool
call or an *out-of-order* one (see G02, G08).
"""

import json
import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv
from langfuse import Langfuse, observe
from pydantic import BaseModel, Field, ValidationError

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    if not os.environ.get(var):
        raise RuntimeError(
            f"{var} not set. Add it to .env at the repo root "
            "(cloud.langfuse.com has a free tier), then re-run."
        )

client = Anthropic()
MODEL = "claude-sonnet-5"
langfuse = Langfuse()

LAB_DIR = os.path.dirname(os.path.abspath(__file__))
GOLDENS_PATH = os.path.join(LAB_DIR, "goldens.json")


def load_goldens(path=GOLDENS_PATH):
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
    return 1 if conversation["expected_resolution"] else 0


def trajectory_score(conversation: dict) -> float:
    """
    TODO 2 — Trajectory scorer.

    Compare conversation["agent_actions"] (what actually happened)
    against conversation["expected_actions"] (what should have
    happened) and return a score between 0.0 and 1.0.

    A simple, defensible approach:
      - 1.0 if agent_actions == expected_actions exactlyz
      - 0.0 if any *required* action is missing, or the actions that
        ARE present are in the wrong order
      - Something in between (e.g. 0.85) if the agent did everything
        required, correctly ordered, but added extra/redundant calls

    There's no single "correct" formula here — document whatever rule
    you choose so a teammate could apply it consistently.
    """
    # YOUR CODE HERE
    actual = conversation["agent_actions"]
    expected = conversation["expected_actions"]


    if actual == expected:
        return 1.0

    missing = [a for a in expected if a not in actual]
    if missing:
        return 0.0

    actual_required_order = list(dict.fromkeys(a for a in actual if a in expected))
    if actual_required_order != expected:
        return 0.0

    extra_calls = len(actual) - len(expected)
    penalty = min(0.15 * extra_calls, 0.3)

    return round(1.0 - penalty, 2)


def combined_score(res_score: int, traj_score: float) -> float:
    """
    TODO 3 — Combine the two lenses into one number for triage.

    Suggested starting weights: 60% resolution, 40% trajectory — but
    feel free to justify a different split (e.g. should a resolved
    conversation that broke policy still score highly?).
    """
    # YOUR CODE HERE
    return round(0.6 * res_score + 0.4 * traj_score, 2)


# --- Given: LLM-as-judge + Langfuse tracing (no TODOs below) -------------
# Wraps whatever your three scorers above return into one Langfuse trace
# per golden, plus a real Claude call grading the agent's actual reply.


class JudgeVerdict(BaseModel):
    score: int = Field(ge=1, le=5, description="1=poor, 5=excellent, on tone + policy adherence")
    rationale: str = Field(description="One sentence justifying the score")


JUDGE_TOOL = {
    "name": "submit_verdict",
    "description": "Submit the judged quality score for this agent reply.",
    "input_schema": JudgeVerdict.model_json_schema(),
}


@observe(as_type="generation", name="llm_judge")
def llm_judge_score(golden: dict) -> JudgeVerdict:
    """Real Claude call grading the agent's final reply against the
    customer's message and the policy notes for this golden — a check no
    amount of static goldens.json fields can do on their own."""

    
    prompt = f"""Customer said: "{golden['customer_message']}"
Actions the agent actually took, in order: {golden['agent_actions']}
Agent's final reply: "{golden['agent_final_message']}"
Policy notes for this scenario: {golden.get('policy_notes', '(none)')}

Grade the agent's reply from 1-5 on tone (empathetic, clear, professional)
AND policy adherence. Base policy adherence on the ACTION LIST above, not
on whether the final reply explicitly restates an action in words — e.g.
if "verify_identity" is in the action list, identity WAS verified even
though a natural reply wouldn't say "I verified your identity" out loud.
Only dock policy points for what policy_notes explicitly flags as wrong,
or for actions genuinely missing from the list."""

    response = client.messages.create(
        model=MODEL, max_tokens=200,
        tools=[JUDGE_TOOL], tool_choice={"type": "tool", "name": "submit_verdict"},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    try:
        return JudgeVerdict(**tool_call.input)
    except ValidationError as e:
        raise RuntimeError(f"Judge returned a malformed verdict: {e}")


@observe(name="eval_golden")
def evaluate_golden(golden: dict) -> dict:
    r = resolution_score(golden)
    t = trajectory_score(golden)
    c = combined_score(r, t)
    judge = llm_judge_score(golden)

    langfuse.update_current_span(
        name=f"eval_{golden['id']}",
        input=golden["customer_message"],
        output=golden["agent_final_message"],
        metadata={"intent": golden["intent"], "policy_notes": golden.get("policy_notes", "")},
    )
    langfuse.score_current_trace(name="resolution", value=r, data_type="NUMERIC")
    langfuse.score_current_trace(name="trajectory", value=t, data_type="NUMERIC")
    langfuse.score_current_trace(name="combined", value=c, data_type="NUMERIC")
    langfuse.score_current_trace(name="llm_judge", value=judge.score, data_type="NUMERIC",
                                  comment=judge.rationale)

    return {
        "id": golden["id"], "intent": golden["intent"],
        "resolution": r, "trajectory": round(t, 2), "combined": round(c, 2),
        "judge_score": judge.score, "judge_rationale": judge.rationale,
    }


def run_report(goldens_path=GOLDENS_PATH, flag_threshold=0.6):
    goldens = load_goldens(goldens_path)

    print(f"{'ID':<5}{'Intent':<22}{'Resolution':<12}{'Trajectory':<12}"
          f"{'Combined':<10}{'Judge':<7}Flag")
    print("-" * 90)

    results = []
    for g in goldens:
        row = evaluate_golden(g)
        results.append(row)
        flag = row["combined"] < flag_threshold or row["judge_score"] <= 2
        print(f"{row['id']:<5}{row['intent']:<22}{row['resolution']:<12}"
              f"{row['trajectory']:<12}{row['combined']:<10}{row['judge_score']:<7}"
              f"{'[REVIEW]' if flag else ''}")
        if flag:
            print(f"      judge: {row['judge_rationale']}")

    avg_combined = sum(r["combined"] for r in results) / len(results)
    avg_judge = sum(r["judge_score"] for r in results) / len(results)
    print(f"\nSuite summary: avg combined = {avg_combined:.2f}, "
          f"avg LLM-judge score = {avg_judge:.1f}/5")

    langfuse.flush()
    host = (os.environ.get("LANGFUSE_BASE_URL")
            or os.environ.get("LANGFUSE_HOST")
            or "https://cloud.langfuse.com")
    print(f"\nTraces + scores flushed to Langfuse — view them at {host}")


if __name__ == "__main__":
    run_report()
