"""
Day 5 · Pre-Lunch Lab H1 (Insurance) — Resolution + Trajectory Eval Suite
==========================================================================
FACILITATOR REFERENCE SOLUTION — one valid way to complete the lab.
Participants' scoring rules do not need to match this exactly; what
matters is that they can justify their weighting and their trajectory
comparison logic.

This version also traces every golden through Langfuse and adds an
LLM-as-judge pass over the agent's final reply — see eval_suite_starter.py
for what's given vs. what participants implement.
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

# Expected: G02's known identity-verification violation and G06's
# incomplete trajectory should pull both trajectory and judge_score down.
# After running, each golden is a separate trace in the Langfuse UI with
# all four scores attached — something a terminal table alone can't give
# a facilitator reviewing results after the fact.
