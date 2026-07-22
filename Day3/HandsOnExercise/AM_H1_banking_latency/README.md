# AM · H1 — Banking: Voice Loop + Latency Measurement

**Track:** Banking | **Time box:** ~40 min | **Pattern practiced:** instrumented STT → LLM → TTS pipeline against the round-trip latency budget, with a genuinely-measured time-to-first-token

## A note on this lab's simulation
This training room doesn't have microphones, phone lines, or API keys for
Deepgram/Cartesia wired up for every student. So this lab **simulates the
audio layer** — `fake_stt()` and `fake_tts()` stand in for real STT/TTS
calls, with `time.sleep()` durations modeled on real published latencies
for Deepgram Nova-3 and Cartesia Sonic-3. The **LLM call is real and
streamed** — that part isn't simulated at all. The pipeline shape, the
timing instrumentation, and the budget math are exactly what you'd build
against a real LiveKit/Pipecat + Deepgram + Cartesia stack — swapping the
audio fakes for real SDK calls later is a drop-in replacement, not a redesign.

## Scenario
A banking customer calls in asking "What's my account balance?" Your job
today isn't to make the agent smarter — it's to make the round trip fast
enough that the conversation feels natural. ITU-T G.114 says round-trip
delay above ~700ms starts to feel sluggish to a human listener; production
voice agents target the 500-700ms band end to end.

## Your task
Build an instrumented pipeline:
1. `fake_stt(user_utterance)` — simulates a streaming STT call. Sleep for a
   realistic Deepgram Nova-3-like latency, then return a transcript string.
2. `call_llm_streaming(transcript)` — a REAL, STREAMED call to Claude.
   Measure time-to-first-token by timestamping the moment the first chunk
   arrives from `stream.text_stream`, not just when the whole thing finishes.
   Return the full text, the time-to-first-token, and the full completion
   time (both — you want to see the gap between them).
3. `fake_tts(text)` — simulates Cartesia Sonic-3's sub-100ms *time-to-first-audio-byte*,
   then returns a fake "audio bytes" placeholder.
4. `run_turn(user_utterance)` — runs stt → llm → tts, and computes
   **TIME TO FIRST AUDIO = stt_ms + llm_time_to_first_token_ms + tts_ms** —
   deliberately NOT stt + llm_full_completion + tts. Time to first audio is
   what a caller actually perceives as "did it respond quickly," since a
   real pipeline starts speaking as soon as enough text exists, not after
   the whole reply is generated.

Run it for 3 different customer utterances and look at where the time
actually goes — and how much smaller time-to-first-token is than full
completion time.

## Why this matters
This is today's Topic 01 (the voice pipeline) and Topic 02/03 (STT/TTS
vendor choice) made concrete: the budget is not evenly split three ways —
the LLM's time-to-first-token is usually the largest and least predictable
chunk, which is why production systems stream every stage rather than
waiting for each one to fully finish before starting the next. This lab
measures that claim instead of just asserting it — the gap you'll see
between `llm_time_to_first_token_ms` and `llm_full_completion_ms` is real
latency a non-streaming pipeline would leave on the table.

## Files
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Have `fake_tts` start on the first SENTENCE (split on `. ` / `? ` / `! `)
  rather than the first token — closer to how a real pipeline chunks text
  for TTS, and a fairer test of "can we start speaking sooner."
- Run 20 turns and report P50/P95/P99 for TIME TO FIRST AUDIO instead of
  one sample (this previews this afternoon's Topic 02, Latency Engineering).

## Discussion (bring back to the group)
- You now have two real numbers: time-to-first-token and full completion
  time. If a pipeline only ever reports the total, what decision might a
  team make incorrectly because they can't see this gap?

---

## Alt-stack variant (optional)
`solution_real_voice.py` — same latency-budget measurement, with
fake_stt()/fake_tts() swapped for real Deepgram Nova-3 (STT) and
ElevenLabs Flash v2.5 (TTS) calls. Needs `DEEPGRAM_API_KEY` +
`ELEVENLABS_API_KEY`, and a few short WAV recordings (see the file's
docstring for setup). See `requirements-multisdk.txt`.
