# AM · H2 — Insurance: Tune Turn-Taking to Cut False Interruptions

**Track:** Insurance | **Time box:** ~45 min | **Pattern practiced:** endpointing thresholds (customer→agent) AND barge-in cancellation (agent→customer) — turn-taking runs both directions

## A note on this lab's simulation
No real microphone or VAD model here either — instead you get pre-recorded
**silence-gap sequences**: lists of (speech_ms, silence_ms) segments that
model what a Voice Activity Detector would report for real calls,
including calls where the customer pauses mid-thought ("I was in an
accident on... um... July 3rd") without meaning to yield the floor. The
**endpointing decision logic you write today is the same logic a real VAD
integration hangs off** — only the signal source changes. Part 2's
"TTS playback" is a simulated word-by-word print loop, not real audio —
but the cancellation mechanism (`asyncio.Task.cancel()`) is the real
mechanism production frameworks use.

## Part 1 — Endpointing (customer's turn ending)
A naive voice agent ends the customer's turn the instant it detects any
silence — which means a customer who pauses to think ("I need to file a
claim for... um...") gets cut off mid-sentence by the agent jumping in.
That's a **false interruption**, and it's one of the most common complaints
about early voice agents. Tune the endpointing threshold to reduce false
interruptions without making the agent feel sluggish.

1. `is_turn_complete(silence_ms, threshold_ms)` — the naive version:
   return `True` once silence_ms >= threshold_ms.
2. Run the provided `test_calls` (in `test_calls.json`) through a fixed
   threshold (start with 300ms) and count: how many calls had the agent
   interrupt mid-thought (a "false interruption," marked in the test data)
   vs. correctly wait for the real end of turn.
3. Sweep the threshold from 200ms to 1000ms in 100ms steps and print a
   table: threshold → false interruption count → average response delay
   (a longer threshold reduces false interruptions but adds latency to
   every turn — that trade-off is the point).
4. Implement one improvement beyond a fixed threshold: a
   `is_turn_complete_smart(transcript_so_far, silence_ms)` that also checks
   whether the transcript so far ends on a filler word ("um", "uh", "so",
   "and") or trails off — and if so, applies a longer threshold for that
   pause specifically, rather than raising the threshold for every pause.

## Part 2 — Barge-in (agent's turn ending, required)
Turn-taking isn't just about when the CUSTOMER is done — a good voice
agent must also be interruptible when the CUSTOMER starts talking while
the AGENT is still speaking (barge-in). Build:

1. `simulate_tts_playback(text, chunk_delay=0.15)` — an `async def` that
   prints the reply word by word with an `await asyncio.sleep(chunk_delay)`
   between each, standing in for streamed audio playback.
2. `InterruptionManager` — tracks the currently-playing `asyncio.Task` and
   whether the agent `is_speaking`. Its `barge_in()` method: if currently
   speaking, call `.cancel()` on the playback task and set `is_speaking =
   False`; return whether a cancellation actually happened.
3. A demo in `__main__` (provided, `asyncio.run(...)`) that starts a
   playback task, waits a short delay to simulate a customer starting to
   talk mid-reply, calls `barge_in()`, and confirms (via
   `asyncio.CancelledError`) that playback stopped immediately rather than
   finishing the sentence.

## Why this matters
This is today's Topic 05 (turn-taking & interruptions), both halves. A
single global threshold is a blunt instrument for Part 1 — the real skill
is recognizing that not all silences mean the same thing. Part 2 is the
mirror image: an agent that can't be interrupted mid-sentence reads as
unresponsive or robotic, and in production this is exactly why frameworks
build turn-taking around cancellable async tasks rather than
"play the whole thing no matter what."

## Files
- `test_calls.json` — silence-gap sequences with ground-truth end-of-turn labels.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
python starter.py
```
No API key needed for this lab — it's pure control-flow logic (Part 1)
plus `asyncio` task management (Part 2), no LLM call required.

## Stretch goals
- Weight the false-interruption cost against the added-latency cost and
  compute a single score per threshold, so you can argue for a specific
  number instead of eyeballing the table.
- Add a second smart signal: rising vs. falling intonation is a real VAD
  feature in production systems — simulate it as a boolean flag on each
  test segment and factor it into `is_turn_complete_smart`.
- Part 2: only barge-in if the customer's incoming speech lasts more than
  ~200ms (a cough or a single "uh" shouldn't cancel the whole reply) —
  add a minimum-duration threshold before triggering `barge_in()`.

## Discussion (bring back to the group)
- Your smart threshold reduces false interruptions on the filler-word
  cases. What's a failure mode it *doesn't* catch — a way a customer could
  still get cut off that filler-word detection wouldn't help with?
- Part 2 cancels immediately on any detected speech. What's the risk of
  that being TOO sensitive — and how would you decide the right
  sensitivity without real user testing?
