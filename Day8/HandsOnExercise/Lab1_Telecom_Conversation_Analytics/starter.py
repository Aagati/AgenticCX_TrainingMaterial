"""
Lab-1: Telecom - Nobody Can Tell You Which Conversations Are Failing (STARTER).

conversation_logs.json is 24 transcripts, six days, three channels. Some of
what you'd want to know about them is FREE — channel, day, resolved, csat are
already fields on the record, no model needed. But the analytics questions
that actually matter ("how many of these needed a supervisor and never got
one?") only exist INSIDE the transcript text — you can't group-by your way to
sentiment. That's the line this lab draws: MetricsEngine computes what the
log already knows; InsightBatchExtractor pays a model call, once per
conversation, to read what the log doesn't.

You'll build:
  1. MetricsEngine — six small deterministic aggregations over the raw log.
  2. InsightBatchExtractor — one tool-forced haiku request per conversation,
     submitted as a single Message BATCHES API job (not 24 sync calls) and
     polled to completion.
  3. InsightAggregator — stats over the batch's output (sentiment,
     escalation rate, top intents) — things the raw log can't tell you.
  4. Dashboard.build — a 3x2 matplotlib PNG: 4 snapshot panels over the
     current run, plus 2 trend panels read back from analytics_runs.json
     so a SECOND run actually shows a line, not just another snapshot.
  5. append_run — persists one run record to analytics_runs.json so a
     second run shows a trend, not just a snapshot.
"""

import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_CHEAP = "claude-haiku-4-5-20251001"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "conversation_logs.json", encoding="utf-8") as f:
    CONVERSATIONS = json.load(f)["conversations"]

RUN_HISTORY_FILE = DATA_DIR / "analytics_runs.json"
DASHBOARD_FILE = DATA_DIR / "dashboard.png"

client = Anthropic()

# Chart chrome — dataviz skill's validated reference palette (light mode; this
# dashboard is a static file, not a themed page).
INK = "#0b0b0b"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
CATEGORICAL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a"}
SEQUENTIAL_5 = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]  # CSAT 1..5, steps 250/350/450/550/650
DIVERGING = {"negative": "#e34948", "neutral": "#c3c2b7", "positive": "#2a78d6"}


class InsightExtraction(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"] = Field(
        description="Overall customer sentiment across the transcript."
    )
    primary_intent: str = Field(description="Short snake_case label, e.g. 'network_outage', 'billing_dispute'.")
    needs_escalation: bool = Field(
        description="True if a human supervisor should have been looped in, whether or not one was."
    )
    key_issue: str = Field(description="One short sentence summarizing what actually happened.")


def format_transcript(conversation: dict) -> str:
    """Given — turns a transcript's turn list into a readable block for the model."""
    return "\n".join(f"{turn['role']}: {turn['text']}" for turn in conversation["transcript"])


class MetricsEngine:
    """Deterministic aggregation over conversation_logs.json alone — zero
    model calls, zero cost, safe to re-run as often as you like."""

    @staticmethod
    def volume_by_channel(conversations: list[dict]) -> Counter:
        """
        TODO 1a: Count conversations per `channel`.
        """
        raise NotImplementedError

    @staticmethod
    def volume_by_day(conversations: list[dict]) -> dict:
        """
        TODO 1b: Count conversations per `date`, returned sorted ascending
        by date (a plain dict preserves insertion order — insert in sorted
        date order).
        """
        raise NotImplementedError

    @staticmethod
    def volume_by_segment(conversations: list[dict]) -> Counter:
        """
        TODO 1c: Count conversations per `segment`.
        """
        raise NotImplementedError

    @staticmethod
    def containment_rate(conversations: list[dict]) -> float:
        """
        TODO 1d: Fraction of conversations where `resolved` is true.
        Round to 3dp. Guard the empty-list case (return 0.0).
        """
        raise NotImplementedError

    @staticmethod
    def csat_stats(conversations: list[dict]) -> dict:
        """
        TODO 1e: Only over conversations where `csat` is not null: return a
        dict with `average` (round 2dp), `response_rate` (responses /
        total conversations, round 3dp), and `distribution` (a dict keyed
        "1".."5" -> count, every key present even if 0). Guard the
        no-responses case (average 0.0).
        """
        raise NotImplementedError

    @staticmethod
    def repeat_contact_rate(conversations: list[dict]) -> float:
        """
        TODO 1f: Group by `customer_id`. Of the UNIQUE customers in this
        log, what fraction appear more than once? (Not: what fraction of
        conversations are repeats — the denominator is customers, not
        conversations.) Round to 3dp.
        """
        raise NotImplementedError


class InsightBatchExtractor:
    """The one model-dependent step. One tool-forced haiku request per
    conversation, submitted as a single Batches API job rather than 24
    sequential calls."""

    @staticmethod
    def build_requests(conversations: list[dict]) -> list[dict]:
        """
        TODO 2a: One Batches API request per conversation:
          {"custom_id": conversation["conversation_id"], "params": {...}}
        `params` is shaped exactly like a normal messages.create() call —
        model=MODEL_CHEAP, a system prompt explaining the analyst task
        (read one support transcript, judge sentiment/primary_intent/
        needs_escalation/key_issue), user content = format_transcript(
        conversation) plus the channel/segment for context, and a forced
        tool call on InsightExtraction.model_json_schema(). custom_id is
        how you'll match each result back to its conversation later —
        Batches doesn't preserve request order.
        """
        raise NotImplementedError

    @staticmethod
    def run(conversations: list[dict], poll_interval: float = 5.0, max_wait_seconds: float = 600.0) -> dict:
        """
        TODO 2b: client.messages.batches.create(requests=build_requests(...))
        to submit. Then poll client.messages.batches.retrieve(batch.id)
        in a sleep(poll_interval) loop until .processing_status == "ended"
        (print .request_counts each poll so a long wait isn't silent; give
        up past max_wait_seconds rather than looping forever). Once ended,
        iterate client.messages.batches.results(batch.id) — for each item
        whose .result.type == "succeeded", pull the tool_use block off
        .result.message.content and parse it into an InsightExtraction.
        Skip (don't crash on) any result that isn't "succeeded". Return a
        dict keyed on custom_id -> InsightExtraction.
        """
        raise NotImplementedError


class InsightAggregator:
    """Deterministic stats — but over the MODEL's output, not the raw log.
    This is why it's a separate class from MetricsEngine: everything in
    here was unknowable before InsightBatchExtractor ran."""

    @staticmethod
    def sentiment_breakdown(insights: dict) -> Counter:
        """
        TODO 3a: Count `.sentiment` across all InsightExtraction values.
        """
        raise NotImplementedError

    @staticmethod
    def escalation_rate(insights: dict) -> float:
        """
        TODO 3b: Fraction where `.needs_escalation` is true. Round 3dp.
        Guard the empty case.
        """
        raise NotImplementedError

    @staticmethod
    def top_intents(insights: dict, n: int = 5) -> list:
        """
        TODO 3c: Count `.primary_intent` across all values, return the top
        `n` as a list of (intent, count) tuples, most common first.
        """
        raise NotImplementedError


class Dashboard:
    """Renders one 2x2 PNG. See the module-level palette constants —
    categorical stays in fixed slot order, CSAT uses the sequential ramp
    (low->high = light->dark), sentiment uses the diverging pair (negative/
    positive are true opposites, neutral is the gray midpoint)."""

    @staticmethod
    def build(
        volume_by_channel: Counter,
        volume_by_day: dict,
        csat_stats: dict,
        sentiment_breakdown: Counter,
        history: list[dict],
        out_path: Path,
    ) -> None:
        """
        TODO 4: Build a 3x2 matplotlib figure (figsize around (11, 12),
        facecolor=SURFACE) and savefig it to `out_path`. Top two rows are
        the current-run snapshot:
          - top-left: bar, volume by channel. Bar color per channel from
            CATEGORICAL in a FIXED assignment (e.g. chat->blue, sms->
            orange, voice->aqua) — never cycle the default color rotation.
          - top-right: bar, CSAT distribution (keys "1".."5" in order).
            Bar i's color = SEQUENTIAL_5[i] — low CSAT is the lightest
            step, high CSAT the darkest, so "more-is-darker" reads at a
            glance.
          - mid-left: line, volume by day, sorted date order on the
            x-axis. Single series -> one hue (CATEGORICAL["blue"]).
          - mid-right: bar, sentiment breakdown in the fixed order
            negative/neutral/positive, colored from DIVERGING.
        Bottom row is NEW — a cross-run trend read from `history` (the
        full analytics_runs.json list, most recent run last):
          - bottom-left: line of `r["metrics"]["csat"]["average"]` for
            each record `r` in history, x-axis = run number (1-indexed).
          - bottom-right: line of `r["insight_stats"]["escalation_rate"]`
            the same way, in DIVERGING["negative"].
          With fewer than 2 points a line has nothing to connect —
          plot the single point anyway and add a small "needs 2+ runs for
          a line" note so the panel isn't blank/confusing on a first run.
        Every panel: hairline gridlines (GRIDLINE) behind the marks, no
        chart border/spines beyond a light baseline, direct value labels
        on top of each bar (no separate legend box — a static PNG has no
        hover, so the label IS the tooltip), title in INK, axis ticks in
        INK_MUTED. Close the figure after saving.
        """
        raise NotImplementedError


def append_run(
    metrics: dict, insight_stats: dict, history_path: Path = RUN_HISTORY_FILE
) -> dict:
    """
    TODO 5: Load `history_path` if it exists (a JSON list), else start
    from an empty list. Append one record: {"timestamp": <UTC ISO
    string>, "metrics": metrics, "insight_stats": insight_stats}. Write
    the whole list back with indent=2. Return the record you appended.
    This file is what lets a SECOND run of this script show a trend
    instead of just a snapshot — don't overwrite, append.
    """
    raise NotImplementedError


if __name__ == "__main__":
    print(f"=== Lab-1: Telecom Conversation Analytics — {len(CONVERSATIONS)} conversations ===\n")

    print("--- Deterministic metrics (free, no model call) ---")
    volume_channel = MetricsEngine.volume_by_channel(CONVERSATIONS)
    volume_day = MetricsEngine.volume_by_day(CONVERSATIONS)
    volume_segment = MetricsEngine.volume_by_segment(CONVERSATIONS)
    containment = MetricsEngine.containment_rate(CONVERSATIONS)
    csat = MetricsEngine.csat_stats(CONVERSATIONS)
    repeat_rate = MetricsEngine.repeat_contact_rate(CONVERSATIONS)
    print(f"  Volume by channel: {dict(volume_channel)}")
    print(f"  Volume by day: {volume_day}")
    print(f"  Volume by segment: {dict(volume_segment)}")
    print(f"  Containment rate: {containment}")
    print(f"  CSAT: {csat}")
    print(f"  Repeat-contact rate: {repeat_rate}")

    print(f"\n--- Batch-scoring {len(CONVERSATIONS)} transcripts (Message Batches API) ---")
    t0 = time.time()
    insights = InsightBatchExtractor.run(CONVERSATIONS)
    print(f"  Scored {len(insights)}/{len(CONVERSATIONS)} in {time.time() - t0:.1f}s")

    print("\n--- Insight-derived metrics (required reading the transcript) ---")
    sentiment = InsightAggregator.sentiment_breakdown(insights)
    escalation = InsightAggregator.escalation_rate(insights)
    intents = InsightAggregator.top_intents(insights)
    print(f"  Sentiment breakdown: {dict(sentiment)}")
    print(f"  Escalation rate: {escalation}")
    print(f"  Top intents: {intents}")

    print(f"\n--- Escalation-worthy conversations the log alone can't flag ---")
    for conv_id, insight in insights.items():
        if insight.needs_escalation:
            print(f"  {conv_id}: {insight.key_issue}")

    metrics_snapshot = {
        "volume_by_channel": dict(volume_channel),
        "volume_by_day": volume_day,
        "volume_by_segment": dict(volume_segment),
        "containment_rate": containment,
        "csat": csat,
        "repeat_contact_rate": repeat_rate,
    }
    insight_snapshot = {
        "sentiment_breakdown": dict(sentiment),
        "escalation_rate": escalation,
        "top_intents": intents,
    }
    record = append_run(metrics_snapshot, insight_snapshot)
    print(f"\n--- Run recorded -> {RUN_HISTORY_FILE.name} (timestamp {record['timestamp']}) ---")

    print(f"\n--- Building dashboard -> {DASHBOARD_FILE.name} ---")
    full_history = json.load(open(RUN_HISTORY_FILE, encoding="utf-8"))
    Dashboard.build(volume_channel, volume_day, csat, sentiment, full_history, DASHBOARD_FILE)
    print(f"  Written: {DASHBOARD_FILE} ({len(full_history)} run(s) in trend)")

# Expected (hand-verified against conversation_logs.json):
# 24 conversations, 20 unique customers, 4 repeat customers (CUST-T01/T04/T07/
# T12 each appear twice) -> repeat_contact_rate = 4/20 = 0.2. 7 conversations
# are unresolved (CONV-001/004/007/009/012/016/020) -> containment_rate =
# 17/24 = 0.708. csat: 16 of 24 conversations have a response
# (response_rate=0.667), scores sum to 57 -> average=3.56, distribution
# {"1":1,"2":3,"3":3,"4":4,"5":5}. Sentiment/escalation/intents are REAL model
# judgments over the transcript text, not derivable from the fixture alone --
# don't hardcode an expected count, but CONV-001/004/009/012 (repeated
# unresolved issues, explicit supervisor asks, a business-line outage) are
# good candidates to watch for needs_escalation=true. The batch call is the
# slow part of this script -- observed ~3 minutes for 24 requests in testing,
# but Batches has no fixed SLA (it can be faster or slower), so the poll loop
# prints request_counts each check so a longer wait isn't silent.
