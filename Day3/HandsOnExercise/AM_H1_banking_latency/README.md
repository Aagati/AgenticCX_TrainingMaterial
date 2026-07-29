# AM · H1 — Banking: Voice Loop + Latency Measurement

**Track:** Banking | **Time box:** ~40 min | **Pattern practiced:** instrumented STT → LLM → TTS pipeline against the round-trip latency budget, with a genuinely-measured time-to-first-token

## A note on this lab's simulation
This training room doesn't have microphones or phone lines wired up for
every student, so TTS stays **simulated** — `fake_tts()` stands in for a
real TTS call, with a `time.sleep()` duration modeled on Cartesia Sonic-3's
published time-to-first-audio-byte. STT is different: if you set
`DEEPGRAM_API_KEY` and drop a couple of WAV files into `sample_audio/` (see
Setup below), `run_turn()` calls **real Deepgram Nova-3** — no separate
"real variant" file, it's the same `solution.py`/`starter.py` everyone
runs. No key, no matching WAV, or the account can't reach nova-3? It
transparently falls back to `fake_stt()`, modeled on Nova-3's published
~120-220ms latency — so the lab runs either way, and `stt()` is the seam
that makes the swap invisible to the rest of the pipeline. The **LLM call
is real and streamed** either way — that part was never simulated.

## Scenario
A banking customer calls in asking "What's my account balance?" Your job
today isn't to make the agent smarter — it's to make the round trip fast
enough that the conversation feels natural. ITU-T G.114 says round-trip
delay above ~700ms starts to feel sluggish to a human listener; production
voice agents target the 500-700ms band end to end.

## Your task
Build an instrumented pipeline:
1. `real_stt(audio_path)` — a REAL Deepgram Nova-3 prerecorded-transcription
   call (given `DEEPGRAM_API_KEY` + a WAV file — see Setup). `fake_stt()`
   and the `stt()` dispatcher that falls back to it are already given; you
   only need to fill in the actual Deepgram call.
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
Runs fine with just the above (fake_stt handles every turn). To exercise
the real Deepgram path for TODO 1:
```bash
pip install deepgram-sdk
export DEEPGRAM_API_KEY=...   # already in .env if your room provisioned one
```
Then drop up to 3 short (<10s) mono WAV files into a `sample_audio/`
folder next to this script, named `turn_1.wav`, `turn_2.wav`, `turn_3.wav`
(e.g. record with Windows Voice Recorder). Turns without a matching WAV
just use the simulation — mix and match freely.

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
