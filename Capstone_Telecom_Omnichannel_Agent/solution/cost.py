# -*- coding: utf-8 -*-
"""
Part 6a - Langfuse Cost Tracking (REFERENCE SOLUTION)

Genuinely new ground versus every other Langfuse use in this course: Day5's
eval suite, eval gate, and the ClaimsBot capstone all log QUALITY scores
(task_completion, policy_adherence, ...) to Langfuse, but none of them
ever captures actual token usage or a dollar cost. This module does.

Optional by the same convention as lab30's traced(): with no Langfuse keys
set, record_usage() still builds and returns the ledger row (so Part 6 is
fully gradeable offline), it just skips the two Langfuse calls.
"""

import json
import os
from pathlib import Path

_LANGFUSE_ENABLED = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
)
if _LANGFUSE_ENABLED:
    from langfuse import Langfuse
    langfuse = Langfuse()
else:
    langfuse = None

DATA_DIR = Path(__file__).parent

# Pricing per claude-sonnet-5's standard rate (checked against
# shared/models.md, 2026-07): $3.00 / $15.00 per MTok input/output. A
# temporary $2.00/$10.00 introductory rate applies through 2026-08-31 -
# this lab intentionally prices at the STANDARD post-intro rate so
# expected_total_cost_usd in sample_usage_events.json doesn't go stale
# once the intro window ends. cache_read is ~0.1x the input rate, per
# Anthropic's prompt-caching pricing rule (cache reads cost ~0.1x base
# input price).
PRICING = {
    "claude-sonnet-5": {
        "input_per_mtok": 3.00,
        "output_per_mtok": 15.00,
        "cache_read_per_mtok": 0.30,
    },
}

RUN_BUDGET_USD = 0.10
PER_CONVERSATION_BUDGET_USD = 0.03

USAGE_LEDGER: list[dict] = []


def load_sample_usage() -> list[dict]:
    """Given: loads the recorded, self-describing usage fixture used to
    grade Part 6 offline with zero API key. It carries its own
    expected_total_cost_usd / expected_by_agent_role, so model-price
    drift never breaks grading - re-price the fixture, not the test."""
    with open(DATA_DIR / "sample_usage_events.json") as f:
        return json.load(f)["events"]


def _row_cost_usd(row: dict) -> float:
    """Given: the shared pricing formula both record_usage() and
    cost_report() build on. A USAGE_LEDGER row already carrying cost_usd
    (from record_usage) is returned as-is; a raw event straight from
    sample_usage_events.json (which only has token counts) has its cost
    computed on the fly - so cost_report() works on either shape without
    the caller needing to pre-process the fixture."""
    if "cost_usd" in row:
        return row["cost_usd"]
    rates = PRICING[row["model"]]
    return (
        row["input_tokens"] * rates["input_per_mtok"]
        + row["output_tokens"] * rates["output_per_mtok"]
        + row.get("cache_read_tokens", 0) * rates["cache_read_per_mtok"]
    ) / 1_000_000


def record_usage(response, agent_role: str, session_id: str, turn_id: int) -> dict:
    """Compute the dollar cost of one model call and append it to
    USAGE_LEDGER (and, if Langfuse is configured, log it to the active
    trace). This is the multi-agent-specific payoff: candidates see that
    the supervisor's relay turn costs real money too, and that a
    routing-ping-pong transcript roughly doubles the bill."""
    row = {
        "session_id": session_id,
        "turn_id": turn_id,
        "agent_role": agent_role,
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
    }
    row["cost_usd"] = _row_cost_usd(row)
    USAGE_LEDGER.append(row)

    if langfuse is not None:
        langfuse.update_current_span(metadata=row)
        langfuse.score_current_trace(name="cost_usd", value=row["cost_usd"], data_type="NUMERIC")

    return row


def cost_report(ledger: list[dict] | None = None) -> dict:
    """Aggregate a usage ledger into a run-level cost report."""
    ledger = USAGE_LEDGER if ledger is None else ledger

    total_input_tokens = sum(row["input_tokens"] for row in ledger)
    total_output_tokens = sum(row["output_tokens"] for row in ledger)
    costs = [_row_cost_usd(row) for row in ledger]
    total_cost_usd = sum(costs)

    by_agent_role: dict[str, float] = {}
    for row, row_cost in zip(ledger, costs):
        by_agent_role[row["agent_role"]] = by_agent_role.get(row["agent_role"], 0.0) + row_cost

    by_session: dict[str, float] = {}
    for row, row_cost in zip(ledger, costs):
        by_session[row["session_id"]] = by_session.get(row["session_id"], 0.0) + row_cost

    conversations = len(by_session)
    cost_per_conversation = total_cost_usd / conversations if conversations else 0.0

    budget_exceeded = total_cost_usd > RUN_BUDGET_USD or any(
        cost > PER_CONVERSATION_BUDGET_USD for cost in by_session.values()
    )

    return {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": total_cost_usd,
        "by_agent_role": by_agent_role,
        "conversations": conversations,
        "cost_per_conversation": cost_per_conversation,
        "budget_exceeded": budget_exceeded,
    }


if __name__ == "__main__":
    report = cost_report(load_sample_usage())
    print(json.dumps(report, indent=2))

# Expected (against sample_usage_events.json):
#   total_input_tokens  = 7400
#   total_output_tokens = 1350
#   total_cost_usd      = 0.04245  (see the file's own expected_total_cost_usd)
#   by_agent_role has exactly 4 keys: supervisor, billing_agent, plans_agent, tech_agent
#   conversations = 3, budget_exceeded = False (well under both budgets)
