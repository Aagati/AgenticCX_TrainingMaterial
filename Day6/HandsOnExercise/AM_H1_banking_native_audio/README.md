# AM · H1 — Banking: Pipeline vs. Native Audio

**Track:** Banking | **Time box:** ~40 min | **Pattern practiced:** running the same customer turn through a 3-hop modular pipeline and a 1-hop native-audio model, and measuring the difference instead of asserting it

## A note on this lab's simulation
The modular path's LLM stage is a **real, streamed Claude call** (same as
Day 3's AM_H1) — only STT/TTS are simulated, no microphones needed. The
native path is different: if you set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`),
`run_native_turn()` opens a **real Gemini Live API session** on a
native-audio-dialog model and gets back real synthesized audio bytes. No
key, SDK import failure, or a runtime error on the call? It transparently
falls back to a single-hop simulated latency draw — so the lab runs either
way, and `run_native_turn()` is the seam that makes the swap invisible to
`compare_turn()`.

## Scenario
A banking customer calls in with three different requests. You're not
building a smarter agent today — you're building the SAME agent two
different ways, to see what "pipeline to native audio" (today's Topic 01)
actually costs and saves.

## Your task
1. `call_llm_streaming(transcript)` — real streamed Claude call, same shape
   as Day 3's AM_H1: return `(reply_text, elapsed_seconds)`.
2. `run_modular_turn(user_utterance)` — time `fake_stt` → `call_llm_streaming`
   → `fake_tts` as three discrete hops, sum them into `total_ms`.
3. `_run_native_turn_async(user_utterance)` — open a Gemini Live session,
   send the utterance as a text turn, receive audio deltas back, and time
   from connection-open to first audio byte. One hop, no separate stages.
4. `compare_turn(user_utterance)` — run both, print each breakdown, print
   the delta and which path won.

Run it for 3 different customer utterances.

## Why this matters
This is today's Topic 01 made concrete, with a live number attached instead
of a slide. The modular stack (Day 3's whole build) pays for three
independent latency draws — STT, LLM, TTS — each with its own vendor, its
own failure mode, its own budget line. A native-audio model collapses all
three into one model call that reasons over audio and produces audio
directly. That's a straight trade: fewer hops and less integration surface,
against less control over any single stage (you can't swap in a different
STT vendor mid-pipeline if the "STT" is now inside the model). That trade
is this morning's Topic 06, **Gemini vs. the modular stack** — this lab is
the empirical half of that conversation; the discussion prompt below is the
judgment half.

**Where the managed platforms sit (Topic covering Gemini Enterprise Agent
Platform / Customer Engagement Suite / CX Agent Studio):** everything in
this lab talks to the Live API directly — you own the session, the
reconnect logic, the audit trail. Google also ships managed layers on top
of the same models: **Gemini Enterprise Agent Platform** (agent
orchestration + deployment), **Customer Engagement Suite** (a packaged CX
product built on it, closer to a Dialogflow CX successor), and **CX Agent
Studio** (the no/low-code authoring surface for that suite). None of them
change what you measured above — they change who operates the session
lifecycle and how much of PM·H1-H3's plumbing you'd have to build
yourself vs. get for free. Worth naming so "build the Live API session by
hand" doesn't look like the only option in production.

## Files
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic google-genai
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```
Runs fine with just the above (native path uses simulation). To exercise
the real Gemini Live path:
```bash
export GEMINI_API_KEY=...   # ai.google.dev — free tier is enough for this lab
```

## Stretch goals
- Send the SAME three utterances as one multi-turn Live session (reuse the
  connection instead of opening a new one per turn) — measure whether the
  first turn's connection handshake cost disappears for turns 2 and 3, the
  same "warm connection" win Day 3's PM·H2 measured for TTS websockets.
- Add a 4th "hop-count" column that also prices out API calls per turn
  (modular = 2 vendor calls + 1 LLM call; native = 1 call) — turn the
  latency comparison into a cost comparison too.

## Discussion (bring back to the group)
- Native audio wins on latency and integration surface in this lab. Name
  one thing the modular stack still gives you that a single native-audio
  call doesn't — think about what happens when you need to swap ONE stage
  (say, a better STT vendor for accented speech) without touching the rest.
