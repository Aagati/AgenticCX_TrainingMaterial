"""
Day 5 - Pre-Lunch Lab H1 (Insurance) - Resolution + Trajectory Eval Suite
(Langfuse-traced + LLM-as-judge VARIANT)
==========================================================================
eval_suite_solution.py's goldens.json bakes "expected_resolution" and
"expected_actions" straight into the fixture, so its scorers are pure
Python - no LLM call, no observability platform, exactly the two rows the
contents.md "Eval & observability" line names (LangSmith/Langfuse,
LLM-as-judge) and this repo had zero coverage of.

This file keeps eval_suite_solution.py's deterministic resolution_score()/
trajectory_score() (imported, not reimplemented - same ground truth, same
logic) and adds:
  1. An LLM-as-judge pass over agent_final_message - a real Claude call
     grading tone/policy-adherence, something the static golden fields
     can't capture on their own.
  2. Every golden's evaluation wrapped in a Langfuse trace (@observe), with
     all four scores (resolution, trajectory, combined, judge) logged via
     score_current_trace() - so a facilitator can open the Langfuse UI and
     see per-conversation traces instead of only a terminal table.

Setup:
    pip install langfuse
    Set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST in .env
    (placeholders already added; cloud.langfuse.com has a free tier).
    Uses ANTHROPIC_API_KEY (already in .env) for the judge call.
"""

import json
import os
import sys

from anthropic import Anthropic
from langfuse import Langfuse, observe
from pydantic import BaseModel, Field, ValidationError

from eval_suite_solution import (
    load_goldens,
    resolution_score,
    trajectory_score,
    combined_score,
)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
    if not os.environ.get(var):
        raise RuntimeError(
            f"{var} not set. Add it to .env at the repo root "
            "(cloud.langfuse.com has a free tier), then re-run."
        )

client = Anthropic()
MODEL = "claude-sonnet-5"
langfuse = Langfuse()


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
    customer's message and the policy notes for this golden - a check no
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


def run_report(goldens_path="goldens.json", flag_threshold=0.6):
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
    print(f"\nTraces + scores flushed to Langfuse - view them at {host}")


if __name__ == "__main__":
    run_report()

# Expected: same resolution/trajectory numbers as eval_suite_solution.py
# (imported, not reimplemented) plus a judge_score per golden - G02's known
# identity-verification violation and G06's incomplete trajectory should
# pull both trajectory and judge_score down. After running, each golden is
# a separate trace in the Langfuse UI with all four scores attached -
# something a terminal table alone can't give a facilitator reviewing
# results after the fact.
