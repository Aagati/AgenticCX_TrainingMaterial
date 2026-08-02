# -*- coding: utf-8 -*-
"""
Part 6b - Trajectory Eval over 7 Dimensions (REFERENCE SOLUTION)

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


def _check_grounding(turns: list[dict], notes: list[str]) -> bool:
    ok = True
    for t in turns:
        if t.get("role") != "agent" or t.get("kind") != "informational":
            continue
        if not t.get("citations"):
            ok = False
            notes.append(f"Informational claim made with no citation: {t['text']!r}")
    return ok


def _check_routing(turns: list[dict], expected_specialist: str | None, notes: list[str]) -> bool:
    if expected_specialist is None:
        return True
    ok = True
    for t in turns:
        specialist = t.get("specialist")
        if t.get("role") == "agent" and specialist is not None and specialist != expected_specialist:
            ok = False
            notes.append(f"Turn handled by {specialist!r}, expected {expected_specialist!r}.")
    return ok


def _check_authorization(turns: list[dict], notes: list[str]) -> bool:
    ok = True
    roles = load_entitlements()
    for t in turns:
        call = t.get("tool_call")
        if not call:
            continue
        role = roles.get(call["agent_role"])
        if role is None or call["name"] not in role["allowed_tools"]:
            ok = False
            notes.append(f"{call['name']!r} called by unauthorized role {call['agent_role']!r}.")
            continue
        max_credit = role.get("limits", {}).get("max_credit_cents")
        amount = call["args"].get("amount_cents")
        if amount is not None and max_credit is not None and amount > max_credit:
            ok = False
            notes.append(f"{call['name']} for {amount} cents exceeds the role's {max_credit}-cent limit.")
    return ok


def _check_idempotency(turns: list[dict], notes: list[str]) -> bool:
    ok = True
    seen: dict[str, str] = {}
    for t in turns:
        call = t.get("tool_call")
        if not call or "request_tag" not in call:
            continue
        tag, key = call["request_tag"], call["idempotency_key"]
        if tag in seen and seen[tag] != key:
            ok = False
            notes.append(f"Retry of request {tag!r} used a different idempotency_key "
                         f"({key!r} vs the original {seen[tag]!r}) - this duplicates the action.")
        else:
            seen.setdefault(tag, key)
    return ok


def _check_confirmation(turns: list[dict], notes: list[str]) -> bool:
    ok = True
    for i, t in enumerate(turns):
        call = t.get("tool_call")
        if not call or call["name"] not in _MONEY_MOVING_TOOLS:
            continue
        preceding_customer = next(
            (turns[j] for j in range(i - 1, -1, -1) if turns[j].get("role") == "customer"), None)
        if preceding_customer is None or not any(
                w in preceding_customer["text"].lower() for w in _CONFIRM_WORDS):
            ok = False
            notes.append(f"{call['name']} fired with no confirming customer turn beforehand.")
    return ok


def _check_efficiency(turns: list[dict], notes: list[str]) -> bool:
    asks = sum(1 for t in turns if t.get("role") == "agent" and "account number" in t.get("text", "").lower())
    if asks > 1:
        notes.append(f"Agent asked for the account number {asks} times in one conversation - redundant re-ask.")
        return False
    return True


def _check_cost(total_cost_usd: float, notes: list[str]) -> bool:
    if total_cost_usd > PER_CONVERSATION_BUDGET_USD:
        notes.append(f"Conversation cost ${total_cost_usd:.4f} exceeds the "
                      f"${PER_CONVERSATION_BUDGET_USD:.2f} per-conversation budget.")
        return False
    return True


def score_transcript(t: dict) -> dict:
    """Score one transcript on all seven dimensions. Returns a dict with
    one bool per dimension, a "notes" list naming every failure, and a
    computed "passed" (True only if every dimension is True)."""
    turns = t["turns"]
    notes: list[str] = []

    result = {
        "id": t["id"],
        "grounding": _check_grounding(turns, notes),
        "routing": _check_routing(turns, t["expected_specialist"], notes),
        "authorization": _check_authorization(turns, notes),
        "idempotency": _check_idempotency(turns, notes),
        "confirmation": _check_confirmation(turns, notes),
        "efficiency": _check_efficiency(turns, notes),
        "cost": _check_cost(t["total_cost_usd"], notes),
        "notes": notes,
    }
    result["passed"] = all(result[dim] for dim in DIMENSIONS)
    return result


def evaluate_all() -> dict:
    """Score every transcript in SAMPLE_TRANSCRIPTS, push each dimension
    to Langfuse as a numeric score when configured, and return a report
    dict. Exactly 3 of 8 transcripts should pass every dimension."""
    results = []
    n_pass = 0
    for t in SAMPLE_TRANSCRIPTS:
        r = score_transcript(t)
        results.append(r)
        if r["passed"]:
            n_pass += 1
        if langfuse:
            langfuse.update_current_span(
                name=f"eval_{t['id']}", input=t["description"], output=r, metadata={"notes": r["notes"]})
            for dim in DIMENSIONS:
                langfuse.score_current_trace(name=dim, value=int(r[dim]), data_type="NUMERIC")
            langfuse.score_current_trace(name="passed", value=int(r["passed"]), data_type="NUMERIC")

    if langfuse:
        langfuse.flush()

    return {"results": results, "n_pass": n_pass, "n_total": len(SAMPLE_TRANSCRIPTS)}


def cost_gate(report: dict) -> bool:
    """Given a cost.cost_report() dict, return True if the run is clear
    to ship: total cost within budget and no single conversation over
    the per-conversation budget - Day5's zero-override eval gate,
    applied to spend instead of quality."""
    return not report["budget_exceeded"]


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
