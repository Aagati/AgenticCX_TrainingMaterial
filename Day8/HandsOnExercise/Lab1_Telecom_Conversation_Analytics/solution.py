"""
Lab-1: Telecom - Nobody Can Tell You Which Conversations Are Failing.

conversation_logs.json is 24 transcripts, six days, three channels. Some of
what you'd want to know about them is FREE — channel, day, resolved, csat are
already fields on the record, no model needed. But the analytics questions
that actually matter ("how many of these needed a supervisor and never got
one?") only exist INSIDE the transcript text — you can't group-by your way to
sentiment. That's the line this lab draws: MetricsEngine computes what the
log already knows; InsightBatchExtractor pays a model call, once per
conversation, to read what the log doesn't.

Why the Message BATCHES API and not a for-loop of 24 sync calls: this is an
offline scoring job, not a live turn nobody's waiting on. Batches submits all
24 requests as one job, prices at half the per-token rate of synchronous
calls, and is the correct default for "score everything we logged since
yesterday" — the shape almost every real analytics pipeline's model step
actually takes. The trade is latency: a batch isn't instant, so this pipeline
polls instead of blocking on a single response.

MetricsEngine and InsightBatchExtractor's output both feed one Dashboard
(matplotlib, four panels) and one persistent run record
(analytics_runs.json) — the seed of a trend line across days, which is the
whole point of a dashboard that gets run more than once.
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
# dashboard is a static file, not a themed page). Reused as-is by the
# capstone's DashboardNode so every chart this day shares one system.
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
        return Counter(c["channel"] for c in conversations)

    @staticmethod
    def volume_by_day(conversations: list[dict]) -> dict:
        counts = Counter(c["date"] for c in conversations)
        return {day: counts[day] for day in sorted(counts)}

    @staticmethod
    def volume_by_segment(conversations: list[dict]) -> Counter:
        return Counter(c["segment"] for c in conversations)

    @staticmethod
    def containment_rate(conversations: list[dict]) -> float:
        if not conversations:
            return 0.0
        resolved = sum(1 for c in conversations if c["resolved"])
        return round(resolved / len(conversations), 3)

    @staticmethod
    def csat_stats(conversations: list[dict]) -> dict:
        responses = [c["csat"] for c in conversations if c.get("csat") is not None]
        distribution = {str(i): 0 for i in range(1, 6)}
        for score in responses:
            distribution[str(score)] += 1
        average = round(sum(responses) / len(responses), 2) if responses else 0.0
        response_rate = round(len(responses) / len(conversations), 3) if conversations else 0.0
        return {"average": average, "response_rate": response_rate, "distribution": distribution}

    @staticmethod
    def repeat_contact_rate(conversations: list[dict]) -> float:
        by_customer = defaultdict(int)
        for c in conversations:
            by_customer[c["customer_id"]] += 1
        unique = len(by_customer)
        if not unique:
            return 0.0
        repeats = sum(1 for count in by_customer.values() if count > 1)
        return round(repeats / unique, 3)


class InsightBatchExtractor:
    """The one model-dependent step. One tool-forced haiku request per
    conversation, submitted as a single Batches API job rather than 24
    sequential calls."""

    @staticmethod
    def build_requests(conversations: list[dict]) -> list[dict]:
        system = (
            "You are a QA analyst reviewing a single telecom customer-support transcript. Judge "
            "overall sentiment, the primary intent behind the contact, whether this case needed a "
            "human supervisor looped in (regardless of whether one actually was), and summarize the "
            "key issue in one short sentence."
        )
        requests = []
        for conv in conversations:
            user = (
                f"Channel: {conv['channel']}\nSegment: {conv['segment']}\n\n"
                f"Transcript:\n{format_transcript(conv)}"
            )
            requests.append({
                "custom_id": conv["conversation_id"],
                "params": {
                    "model": MODEL_CHEAP,
                    "max_tokens": 300,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                    "tools": [{
                        "name": "record_insight",
                        "description": "Record structured analysis of this support transcript.",
                        "input_schema": InsightExtraction.model_json_schema(),
                    }],
                    "tool_choice": {"type": "tool", "name": "record_insight"},
                },
            })
        return requests

    @staticmethod
    def run(conversations: list[dict], poll_interval: float = 5.0, max_wait_seconds: float = 600.0) -> dict:
        batch = client.messages.batches.create(requests=InsightBatchExtractor.build_requests(conversations))
        print(f"    batch {batch.id} submitted, status={batch.processing_status}")

        waited = 0.0
        while batch.processing_status != "ended":
            if waited >= max_wait_seconds:
                raise TimeoutError(f"Batch {batch.id} still '{batch.processing_status}' after {max_wait_seconds}s")
            time.sleep(poll_interval)
            waited += poll_interval
            batch = client.messages.batches.retrieve(batch.id)
            counts = batch.request_counts
            print(f"    ...{batch.processing_status} (succeeded={counts.succeeded} processing={counts.processing} errored={counts.errored})")

        insights = {}
        for item in client.messages.batches.results(batch.id):
            if item.result.type != "succeeded":
                print(f"    skipping {item.custom_id}: result was '{item.result.type}', not 'succeeded'")
                continue
            tool_call = next(b for b in item.result.message.content if b.type == "tool_use")
            insights[item.custom_id] = InsightExtraction(**tool_call.input)
        return insights


class InsightAggregator:
    """Deterministic stats — but over the MODEL's output, not the raw log.
    This is why it's a separate class from MetricsEngine: everything in
    here was unknowable before InsightBatchExtractor ran."""

    @staticmethod
    def sentiment_breakdown(insights: dict) -> Counter:
        return Counter(insight.sentiment for insight in insights.values())

    @staticmethod
    def escalation_rate(insights: dict) -> float:
        if not insights:
            return 0.0
        flagged = sum(1 for insight in insights.values() if insight.needs_escalation)
        return round(flagged / len(insights), 3)

    @staticmethod
    def top_intents(insights: dict, n: int = 5) -> list:
        return Counter(insight.primary_intent for insight in insights.values()).most_common(n)


class Dashboard:
    """Renders one 2x2 PNG. Categorical stays in fixed slot order, CSAT uses
    the sequential ramp (low->high = light->dark), sentiment uses the
    diverging pair (negative/positive are true opposites, neutral is the
    gray midpoint) — dataviz skill's color-by-job rule applied to each panel."""

    @staticmethod
    def build(
        volume_by_channel: Counter,
        volume_by_day: dict,
        csat_stats: dict,
        sentiment_breakdown: Counter,
        history: list[dict],
        out_path: Path,
    ) -> None:
        fig, axes = plt.subplots(3, 2, figsize=(11, 12), facecolor=SURFACE)
        for ax in axes.flat:
            ax.set_facecolor(SURFACE)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(INK_MUTED)
            ax.tick_params(colors=INK_MUTED, labelsize=9)
            ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
            ax.set_axisbelow(True)

        # top-left: volume by channel — categorical, fixed slot assignment
        ax = axes[0, 0]
        channel_colors = {"chat": CATEGORICAL["blue"], "sms": CATEGORICAL["orange"], "voice": CATEGORICAL["aqua"]}
        channels = [c for c in ("chat", "sms", "voice") if c in volume_by_channel]
        bars = ax.bar(channels, [volume_by_channel[c] for c in channels],
                       color=[channel_colors[c] for c in channels], width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Volume by channel", color=INK, fontsize=11, loc="left", fontweight="bold")

        # top-right: CSAT distribution — sequential, low->high = light->dark
        ax = axes[0, 1]
        scores = ["1", "2", "3", "4", "5"]
        dist = csat_stats["distribution"]
        bars = ax.bar(scores, [dist.get(s, 0) for s in scores], color=SEQUENTIAL_5, width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title(f"CSAT distribution (avg {csat_stats['average']})", color=INK, fontsize=11, loc="left", fontweight="bold")

        # bottom-left: volume by day — single series, one hue
        ax = axes[1, 0]
        days = list(volume_by_day.keys())
        short_days = [d[5:] for d in days]
        values = list(volume_by_day.values())
        ax.plot(short_days, values, color=CATEGORICAL["blue"], linewidth=2, marker="o", markersize=5, zorder=3)
        for x, y in zip(short_days, values):
            ax.annotate(str(y), (x, y), textcoords="offset points", xytext=(0, 6), ha="center", color=INK, fontsize=9)
        ax.set_title("Volume by day", color=INK, fontsize=11, loc="left", fontweight="bold")

        # bottom-right: sentiment — diverging, negative/neutral/positive as true poles
        ax = axes[1, 1]
        sent_order = ["negative", "neutral", "positive"]
        bars = ax.bar(sent_order, [sentiment_breakdown.get(s, 0) for s in sent_order],
                       color=[DIVERGING[s] for s in sent_order], width=0.6, zorder=3)
        ax.bar_label(bars, color=INK, fontsize=9, padding=3)
        ax.set_title("Sentiment breakdown", color=INK, fontsize=11, loc="left", fontweight="bold")

        # bottom row: cross-run trend — the payoff of analytics_runs.json persistence.
        # Every run appends a record; this reads them all back so a dashboard that's
        # been run more than once actually shows a line, not just another snapshot.
        run_idx = list(range(1, len(history) + 1))
        csat_series = [r["metrics"]["csat"]["average"] for r in history]
        escalation_series = [r["insight_stats"]["escalation_rate"] for r in history]

        ax = axes[2, 0]
        if len(history) >= 2:
            ax.plot(run_idx, csat_series, color=CATEGORICAL["blue"], linewidth=2, marker="o", markersize=5, zorder=3)
        else:
            ax.plot(run_idx, csat_series, color=CATEGORICAL["blue"], marker="o", markersize=6, zorder=3)
            ax.set_xlim(0, 2)
            ax.text(0.5, 0.15, "needs 2+ runs for a line", transform=ax.transAxes, ha="center",
                     color=INK_MUTED, fontsize=8)
        ax.set_xticks(run_idx)
        ax.set_title(f"CSAT average across runs (n={len(history)})", color=INK, fontsize=11, loc="left", fontweight="bold")

        ax = axes[2, 1]
        if len(history) >= 2:
            ax.plot(run_idx, escalation_series, color=DIVERGING["negative"], linewidth=2, marker="o", markersize=5, zorder=3)
        else:
            ax.plot(run_idx, escalation_series, color=DIVERGING["negative"], marker="o", markersize=6, zorder=3)
            ax.set_xlim(0, 2)
            ax.text(0.5, 0.15, "needs 2+ runs for a line", transform=ax.transAxes, ha="center",
                     color=INK_MUTED, fontsize=8)
        ax.set_xticks(run_idx)
        ax.set_title(f"Escalation rate across runs (n={len(history)})", color=INK, fontsize=11, loc="left", fontweight="bold")

        fig.suptitle("Telecom Conversation Analytics", color=INK, fontsize=14, fontweight="bold", x=0.02, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_path, dpi=130, facecolor=SURFACE)
        plt.close(fig)


def append_run(metrics: dict, insight_stats: dict, history_path: Path = RUN_HISTORY_FILE) -> dict:
    """Given — every lab this day writes its history to a dedicated JSON
    file, never an in-process dict, so a SECOND run (or another lab reading
    it back) sees a trend, not a snapshot that dies with the process."""
    if history_path.exists():
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "insight_stats": insight_stats,
    }
    history.append(record)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    return record


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
