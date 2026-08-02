# -*- coding: utf-8 -*-
"""
Part 6a - Langfuse Cost Tracking

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


# TODO 10
def record_usage(response, agent_role: str, session_id: str, turn_id: int) -> dict:
    """Compute the dollar cost of one model call and append it to
    USAGE_LEDGER (and, if Langfuse is configured, log it to the active
    trace). This is the multi-agent-specific payoff: candidates see that
    the supervisor's relay turn costs real money too, and that a
    routing-ping-pong transcript roughly doubles the bill.

    Steps:
      1. Read response.model, response.usage.input_tokens,
         response.usage.output_tokens, and
         getattr(response.usage, "cache_read_input_tokens", 0) or 0.
      2. Build the row dict: {"session_id", "turn_id", "agent_role",
         "model", "input_tokens", "output_tokens", "cache_read_tokens"}.
      3. Compute row["cost_usd"] = _row_cost_usd(row) (given helper -
         reuse it, don't re-derive the pricing formula).
      4. Append the row to USAGE_LEDGER.
      5. If langfuse is not None: call
         langfuse.update_current_span(metadata=row) and
         langfuse.score_current_trace(name="cost_usd",
         value=row["cost_usd"], data_type="NUMERIC"). Skip this step
         entirely when langfuse is None - nothing here may ever require
         a Langfuse key to run.
      6. Return the row.
    """
    raise NotImplementedError("TODO: implement record_usage()")


# TODO 11
def cost_report(ledger: list[dict] | None = None) -> dict:
    """Aggregate a usage ledger into a run-level cost report.

    Steps:
      1. ledger = USAGE_LEDGER if ledger is None else ledger.
      2. total_input_tokens / total_output_tokens = sum across all rows.
      3. Compute each row's cost via _row_cost_usd(row) (given helper -
         works whether or not the row already has cost_usd);
         total_cost_usd = sum of those.
      4. by_agent_role: dict mapping each distinct agent_role to the sum
         of its rows' costs.
      5. Group rows by session_id and sum cost per session;
         conversations = number of distinct session_ids present;
         cost_per_conversation = total_cost_usd / conversations (0.0 if
         there are no rows at all, to avoid a division by zero).
      6. budget_exceeded = True if total_cost_usd > RUN_BUDGET_USD, OR if
         any single conversation's summed cost > PER_CONVERSATION_BUDGET_USD.
      7. Return {"total_input_tokens", "total_output_tokens",
         "total_cost_usd", "by_agent_role", "conversations",
         "cost_per_conversation", "budget_exceeded"}.
    """
    raise NotImplementedError("TODO: implement cost_report()")


if __name__ == "__main__":
    report = cost_report(load_sample_usage())
    print(json.dumps(report, indent=2))

# Expected (against sample_usage_events.json):
#   total_input_tokens  = 7400
#   total_output_tokens = 1350
#   total_cost_usd      = 0.04245  (see the file's own expected_total_cost_usd)
#   by_agent_role has exactly 4 keys: supervisor, billing_agent, plans_agent, tech_agent
#   conversations = 3, budget_exceeded = False (well under both budgets)
