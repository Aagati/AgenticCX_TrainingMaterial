# -*- coding: utf-8 -*-
"""
Part 6b - Trajectory Eval over 7 Dimensions

Extends Day5 lab30's exact-pass-count convention (grounding, tool-call
correctness, ...) with three dimensions specific to this capstone:
routing (did the right specialist handle it), authorization (did the
EXECUTING role, not just the replying persona, have permission), and
idempotency (did a retry reuse the original key). Cost is scored
against the SAME PER_CONVERSATION_BUDGET_USD cost.py uses for the run-
level budget gate, so a transcript that blows the budget fails here too.
"""

import json
import os

from cost import PER_CONVERSATION_BUDGET_USD
from permissions import load_entitlements
from sample_transcripts import SAMPLE_TRANSCRIPTS

_LANGFUSE_ENABLED = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
)
if _LANGFUSE_ENABLED:
    from langfuse import Langfuse
    langfuse = Langfuse()
else:
    langfuse = None

DIMENSIONS = ("grounding", "routing", "authorization", "idempotency", "confirmation", "efficiency", "cost")

_CONFIRM_WORDS = ["yes", "confirm", "go ahead", "please", "sure"]
_MONEY_MOVING_TOOLS = ("apply_billing_credit", "change_plan", "create_service_ticket")


# TODO 16
def score_transcript(t: dict) -> dict:
    """Score one transcript (see sample_transcripts.py for the exact
    turn schema) on all seven dimensions. Return a dict with one bool
    per dimension, a "notes" list naming every failure in plain English,
    and a computed "passed" (True only if every dimension is True).

    Each transcript has turns = t["turns"], a list of dicts shaped like:
      {"role": "customer", "text": "..."}
      {"role": "agent", "specialist": "billing"|"plans"|"tech_support",
       "kind": "informational"|"confirmation"|"closing"|"other",
       "text": "...", "citations": [...]}   (citations present iff kind == "informational")
      {"role": "agent", "specialist": "...",
       "tool_call": {"name": "...", "args": {...}, "agent_role": "...",
                     "idempotency_key": "...", "request_tag": "...", "is_retry": bool}}
      {"role": "tool_result", "text": "..."}

    Implement each dimension as follows (a helper function per
    dimension is a reasonable way to organize this, but is not required):

    1. grounding - for every agent turn with kind == "informational",
       its "citations" list must be non-empty. Any informational turn
       with empty/missing citations fails this dimension; note which
       turn's text.

    2. routing - if t["expected_specialist"] is None, this dimension is
       automatically True. Otherwise, every agent turn's "specialist"
       field (when present) must equal t["expected_specialist"]. Note
       any turn handled by the wrong specialist.

    3. authorization - for every turn with a "tool_call", look up
       load_entitlements()[call["agent_role"]]. If the role is unknown,
       OR call["name"] is not in that role's "allowed_tools", this
       dimension fails (note it). If the role has a "max_credit_cents"
       limit and call["args"].get("amount_cents") exceeds it, this
       dimension also fails (note it).

    4. idempotency - for every turn with a "tool_call" that has a
       "request_tag" key, track the FIRST idempotency_key seen for each
       request_tag. If a LATER tool_call reuses the same request_tag
       with a DIFFERENT idempotency_key, this dimension fails (note the
       mismatch) - a genuine retry must reuse the original key.

    5. confirmation - for every turn with a "tool_call" whose name is in
       _MONEY_MOVING_TOOLS, scan backwards from that turn for the
       NEAREST preceding turn with role == "customer". If none exists,
       or its text contains none of _CONFIRM_WORDS (case-insensitive),
       this dimension fails (note it) - the action fired with no
       customer confirmation beforehand.

    6. efficiency - count agent turns whose text contains the phrase
       "account number" (case-insensitive). If more than 1, this
       dimension fails (note the count) - a redundant re-ask.

    7. cost - t["total_cost_usd"] must not exceed PER_CONVERSATION_BUDGET_USD
       (imported above). If it does, this dimension fails (note the
       amount and the budget).

    Return {"id": t["id"], <each dimension>: bool, "notes": [...],
    "passed": all(<the seven dimension values>)}.
    """
    raise NotImplementedError("TODO: implement score_transcript()")


# TODO 17
def evaluate_all() -> dict:
    """Score every transcript in SAMPLE_TRANSCRIPTS, push each dimension
    to Langfuse as a numeric score when configured, and return a report
    dict. Exactly 3 of 8 transcripts should pass every dimension.

    Steps:
      1. results = []; n_pass = 0.
      2. For each t in SAMPLE_TRANSCRIPTS: r = score_transcript(t);
         results.append(r); if r["passed"], increment n_pass.
      3. If langfuse is not None: call
         langfuse.update_current_span(name=f"eval_{t['id']}",
         input=t["description"], output=r, metadata={"notes": r["notes"]}),
         then for each dim in DIMENSIONS, langfuse.score_current_trace(
         name=dim, value=int(r[dim]), data_type="NUMERIC"), then also
         score "passed" the same way.
      4. If langfuse is not None, call langfuse.flush() once at the end.
      5. Return {"results": results, "n_pass": n_pass, "n_total": len(SAMPLE_TRANSCRIPTS)}.
    """
    raise NotImplementedError("TODO: implement evaluate_all()")


# TODO 18
def cost_gate(report: dict) -> bool:
    """Given a cost.cost_report() dict, return True if the run is clear
    to ship: total cost within budget and no single conversation over
    the per-conversation budget - Day5's zero-override eval gate,
    applied to spend instead of quality.

    Steps:
      1. Return `not report["budget_exceeded"]`.
    """
    raise NotImplementedError("TODO: implement cost_gate()")


def print_report(report: dict) -> None:
    """Given: pretty-print an evaluate_all() report."""
    print("\n=== Trajectory Eval Report ===")
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"\n[{status}] {r['id']}")
        print("  " + "  ".join(f"{dim}={r[dim]}" for dim in DIMENSIONS))
        for note in r["notes"]:
            print(f"    - {note}")
    print(f"\n{report['n_pass']}/{report['n_total']} transcripts passed all seven dimensions.")

    if langfuse:
        host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com"
        print(f"\nTraces + scores flushed to Langfuse - view them at {host}")
    else:
        print("\n(Langfuse tracing skipped - set LANGFUSE_PUBLIC_KEY / "
              "LANGFUSE_SECRET_KEY to see this run in the Langfuse UI.)")


if __name__ == "__main__":
    from cost import cost_report, load_sample_usage

    report = evaluate_all()
    print_report(report)

    print("\n=== Cost gate ===")
    usage_report = cost_report(load_sample_usage())
    print(json.dumps(usage_report, indent=2))
    print("Cost gate:", "PASS" if cost_gate(usage_report) else "BLOCKED")

# Expected: exactly 3/8 transcripts pass (T1_clean_credit, T6_correct_escalation,
# T8_clean_plan_change). T2 fails routing only, T3 fails grounding only,
# T4 fails authorization only, T5 fails idempotency only, T7 fails
# efficiency only - each note names the specific problem. Cost gate:
# PASS (sample_usage_events.json is well under both budgets).
