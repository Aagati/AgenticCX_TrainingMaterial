# Lab-1: Telecom - Nobody Can Tell You Which Conversations Are Failing

**Track:** Telecom | **Industry angle:** a week of chat/voice/sms support conversations, and the gap between what the log already knows and what only the transcript knows

## Mental model: two kinds of metric

Every conversation log has two very different kinds of question hiding in it:

```
conversation_logs.json (24 transcripts, 6 days, 3 channels)
        │
        ├──► MetricsEngine ──────────────► volume, containment, CSAT,
        │    (deterministic, free,          repeat-contact rate
        │     zero model calls)
        │
        └──► InsightBatchExtractor ──────► sentiment, escalation rate,
             (ONE Batches API job,          primary intents
              24 requests, one poll loop)
                        │
                        ▼
                 InsightAggregator
                        │
        ┌───────────────┴───────────────┐
        ▼                                ▼
   Dashboard.build()              append_run()
   (matplotlib, 2x2 PNG)          (analytics_runs.json,
                                   persistent, one record per run)
```

`resolved`, `csat`, `channel`, `date` are fields already sitting in the JSON
— counting them is a `Counter`, not an insight. `needs_escalation` and
`sentiment` don't exist anywhere until a model actually reads the transcript.
That split is the lab: cheap deterministic aggregation vs. the one place a
model call is load-bearing.

## Why a BATCH job, not 24 API calls in a loop

A conversation log isn't a live customer waiting on a reply — it's yesterday's
traffic, and you want all 24 (or 24,000) scored before your morning stand-up,
not scored as fast as possible one at a time. That's exactly the Message
**Batches API**'s use case:

| | Sync loop (`for` + `messages.create`) | Batches API |
|---|---|---|
| Shape | N requests, N round trips | N requests, 1 job |
| Price | Standard rate | **50% of standard rate** |
| Latency | Fast per-call, blocks the whole loop | Not instant — observed ~3 min for 24 requests; no fixed SLA |
| Right for | A live turn, someone's waiting | Offline scoring, nobody's watching the clock |

You submit all 24 requests with one `client.messages.batches.create()`,
poll `client.messages.batches.retrieve(batch_id).processing_status` until
it's `"ended"`, then read every result back via
`client.messages.batches.results(batch_id)` — matched to its conversation by
`custom_id`, since a batch doesn't preserve submission order.

## Reading the dashboard

| Panel | Chart type | Why |
|---|---|---|
| Volume by channel | Bar, fixed categorical colors | Channel is an identity, not a magnitude — chat/sms/voice each get their own color slot, always the same one |
| CSAT distribution | Bar, one hue light→dark | CSAT is an ordered scale (1 low → 5 high) — sequential color, not categorical |
| Volume by day | Line, single series | Trend over time |
| Sentiment breakdown | Bar, diverging pair | negative/positive are true opposites; neutral is the gray midpoint — the same color logic as a diverging bar chart, applied to three bars instead of a spectrum |

## Why analytics_runs.json, not a variable

A dashboard that only ever shows ONE run's numbers can't answer "is this
week better or worse than last week." `append_run()` writes a dedicated,
persistent JSON file — every run of this script adds one record, nothing is
overwritten. Run the script twice and you have two data points; that file is
what a real trend dashboard would eventually chart against.

## When to reach for this pattern

- You're logging conversations somewhere and nobody's ever aggregated them
  into a number a stakeholder could act on.
- The question you actually care about ("how many of these needed a human
  and didn't get one") isn't a field in your log — it requires reading the
  text.
- You're scoring a batch of PAST conversations, not reacting to a live one —
  the Batches API is the default for this, not sync calls in a loop.

## Files
- `conversation_logs.json` — 24 transcripts, 6 days, 3 channels, 3 segments,
  20 unique customers (4 with repeat contacts).
- `analytics_runs.json` — created at runtime by `append_run()`; gitignored,
  grows every run. Delete it to reset the trend history.
- `dashboard.png` — created at runtime by `Dashboard.build()`; gitignored,
  overwritten every run.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv matplotlib
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- `InsightBatchExtractor` re-scores all 24 conversations every run, even
  ones a prior run already scored. At what log volume does that stop making
  sense, and what would you key an incremental/"only score what's new"
  version on?
- The escalation-worthy conversations this lab surfaces were never flagged
  as escalations in the source log — they were resolved, tagged, and closed
  as ordinary tickets. What does it mean for a QA process that the only way
  to find them is to re-read every transcript with a model?
- CSAT response_rate here is 0.667 — a third of conversations have no CSAT
  at all. Is a dashboard's CSAT average even meaningful without accounting
  for who chose not to respond?
