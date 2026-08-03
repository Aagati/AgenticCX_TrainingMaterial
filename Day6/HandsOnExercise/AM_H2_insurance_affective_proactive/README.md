# AM · H2 — Insurance: Affective Dialogue & Proactive Audio

**Track:** Insurance | **Time box:** ~40 min | **Pattern practiced:** wiring two Gemini Live API config flags (`enable_affective_dialog`, `proactivity.proactive_audio`) and observing their effect, not just enabling them and moving on

## A note on this lab's simulation
Real affective dialogue reads TONE — pitch, pace, prosody — directly out of
audio the classroom doesn't have microphones for. `detect_affect_cues()` is
a text-only stand-in (keyword + punctuation heuristic) that approximates
what a native-audio model would pick up from a caller's actual voice — it's
there so the exercise has something deterministic to test against, not
because it's how the real feature works. The Live API calls themselves are
**real** if `GEMINI_API_KEY`/`GOOGLE_API_KEY` is set (affective dialogue
additionally needs the `v1alpha` API surface, wired into the client
construction below); both fall back to a rule-based simulation otherwise.

## Scenario
An insurance company is calling policyholders for routine claim check-ins.
Some callers are calm, some are visibly stressed about a denied estimate.
The agent should not sound identical on every call.

## Your task
1. `detect_affect_cues(transcript)` — the text-only affect heuristic.
2. `build_live_config(enable_affect, enable_proactive)` — assemble the
   `LiveConnectConfig` with the right flags set.
3. `_run_affective_turn_async()` — open a session, send one turn, collect
   the reply, with affective dialogue on or off.
4. `compare_affect_modes()` — run the same utterance both ways, print both
   replies side by side.
5. `_listen_for_proactive_async()` — send an opening turn, drain the direct
   reply, then go quiet and see if the model checks in unprompted within a
   timeout window.
6. `listen_for_proactive_checkin()` — dispatcher with the simulated
   fallback rule.

## Why this matters
This is today's Topic 02. Two distinct capabilities get conflated a lot in
vendor decks, so keep them separate in your head: **affective dialogue** is
reactive — the model changes HOW it responds based on what it just heard.
**Proactive audio** is initiative — the model can decide TO respond (or to
interject) without being prompted, based on context like a long silence
after a stressful statement. Both only exist on native-audio-dialog models
(Topic 01's territory) — a modular STT→LLM→TTS pipeline has no channel for
either: STT throws away prosody by the time text reaches the LLM, and
nothing in that pipeline has a notion of "speak without being spoken to."

## Files
- `call_transcripts.json` — 8 labeled sample transcripts (`expected_affect`:
  distressed / neutral / positive) for testing the heuristic.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install google-genai python-dotenv
python starter.py
```
Runs fine with just the above (both features use simulation). To exercise
the real Gemini Live path:
```bash
export GEMINI_API_KEY=...   # ai.google.dev
```

## Stretch goals
- Feed `detect_affect_cues` a transcript that's calm in WORDS but would be
  distressed in TONE if spoken aloud (e.g. "I'm fine, really, it's fine.")
  — confirm the heuristic misses it, and discuss what real audio input
  would catch that text can't.
- Log every `listen_for_proactive_checkin` result across 20 runs per affect
  bucket and report the empirical proactive-response rate instead of
  trusting 3 samples.

## Discussion (bring back to the group)
- Proactive audio means the agent can speak without being asked. In a
  regulated call (recorded, disclosed, consented — PM·H3's territory this
  afternoon), what does an UNPROMPTED agent utterance need to satisfy that
  a reactive one doesn't — who initiated that turn, for compliance
  purposes?
