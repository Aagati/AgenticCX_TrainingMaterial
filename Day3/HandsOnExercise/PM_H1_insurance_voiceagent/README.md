# PM · H1 — Insurance: Voice Agent That Answers a Claim-Status Call

**Track:** Insurance | **Time box:** ~75 min | **Ships:** a working voice agent
**Pattern practiced:** full pipeline assembly — streaming-shaped STT/LLM/TTS with a mid-turn tool call

## Scenario
This morning you measured latency (AM·H1), tuned turn-taking (AM·H2), and
built a call state machine (AM·H3) as three separate exercises. This
afternoon you assemble all three into one real voice agent: a caller asks
about their claim status, the agent has to recognize that requires a tool
call, look it up, and speak back a natural answer — all while staying
inside the latency budget.

## Your task
Build `VoiceAgent`, combining today's morning patterns:
1. **Pipeline** (from AM·H1): `stt()` → LLM → `fake_tts()`, fully
   instrumented with per-stage timing. `stt()` tries a REAL Deepgram
   Nova-3 call (`real_stt()` — your TODO 1) against a WAV in
   `sample_audio/` when `DEEPGRAM_API_KEY` is set, and transparently falls
   back to the simulated `fake_stt()` otherwise — same pattern as AM·H1,
   no separate variant file. TTS stays simulated either way.
2. **Tool-calling mid-turn**: the LLM call must have a `get_claim_status`
   tool available (reuse the Day 2 tool-use loop pattern). When the caller
   asks about a claim, the agent should call the tool, then speak the
   result — and your pipeline must account for tool-call time in the
   latency breakdown, since it adds a second LLM round-trip.
3. **Call state machine** (from AM·H3): wrap the pipeline in the
   RINGING → ANSWERED → IN_PROGRESS → ENDED state machine so this is a
   real call, not just a single Q&A pair.
4. **Endpointing** (from AM·H2, simplified): before generating a reply,
   simulate a silence-gap check using `is_turn_complete` logic with a
   fixed 400ms threshold — don't over-engineer the smart version today,
   just show the seam exists.

## What "ships" means
By the end of this lab you should be able to run `python solution.py` (or
your own build) and see a full simulated call: ring → answer → greeting →
caller asks about claim CLM-3391 → agent calls get_claim_status → agent
speaks the status → caller says thanks → hangup — with a latency
breakdown printed for every turn, including the tool-call turn (which will
be visibly slower — that's expected and worth noting out loud).

## Files
- `claims_data.json` — same shape as Day 2's claims data.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```
Runs fine with just the above (fake_stt handles every turn). To exercise
the real Deepgram path for TODO 1:
```bash
pip install deepgram-sdk
export DEEPGRAM_API_KEY=...   # already in .env if your room provisioned one
```
Then drop up to 2 short (<10s) mono WAV files into a `sample_audio/`
folder next to this script: `turn_1.wav` (the claim-status question),
`turn_2.wav` ("Great, thank you!"). No matching WAV just uses the
simulation for that turn.

## Stretch goals
- Add a second tool (e.g. `get_policy_summary`) and confirm the agent
  picks the right one based on what the caller actually asked.
- Track cumulative call duration and print a final call summary (total
  turns, total latency, tool calls made) when the state machine reaches ENDED.

## Discussion (bring back to the group)
- The tool-call turn roughly doubles LLM latency (two round-trips instead
  of one). In a real system, would you tell the caller something during
  that wait ("Let me pull that up for you...") rather than leaving dead
  air? What would it take to build that in?
