# PM · H3 — Insurance: Latency & Reliability + Compliance

**Track:** Insurance | **Time box:** ~50 min | **Pattern practiced:** the day's capstone — native-audio-first with a real modular failover, timed and logged, wrapped in a disclosure/consent/erasure compliance gate, plus barge-in and a closing reliability+compliance summary

## What this lab is about
A single insurance claims call that has to survive a bad network day, a
regulator's audit request, AND a customer talking over the agent — not
three separate demos, one call, all at once. Six concerns, one
`call_log`:
- **Reliability failover** — native audio is tried first; ANY failure
  (a real exception or a simulated "unreachable" draw) drops to a 3-hop
  modular pipeline, and every turn logs which path served it AND how long
  it took.
- **Compliance gate** — AI disclosure and recording consent logged up
  front; an in-call erasure request short-circuits before any model call.
- **Multimodal redaction** — an attached image is logged as a hash+size
  reference, never raw bytes.
- **Proactive-turn attribution** — an unprompted agent turn gets a
  distinct `agent_initiated=True` tag, because "who spoke first" is a
  compliance fact, not a UX detail.
- **Barge-in** — a customer talking over mid-playback cancels the agent's
  turn immediately instead of finishing it.
- **Call summary** — a closing report that aggregates the whole log into
  one reliability+compliance artifact: path split, latency, failures,
  consent, disclosure, erasure, barge-in.

See the CONCEPT CHEATSHEET below for where each piece lives.

CONCEPT CHEATSHEET
-------------------------------------------------------------------------
| Concept                       | Where                                  |
|--------------------------------|------------------------------------------|
| Native-first reliability failover | run_resilient_turn() / _try_connect_native() |
| Per-turn latency instrumentation | run_resilient_turn()'s timing around each path |
| Modular fallback pipeline     | run_modular_fallback_turn() / call_llm_streaming() |
| AI disclosure + consent       | disclose_ai() / request_recording_consent() / record_consent_response() |
| Multimodal image redaction    | redact_image_ref()                     |
| In-call erasure gate          | check_erasure_request() / handle_customer_turn() |
| Proactive-turn attribution    | log_agent_turn(agent_initiated=True)   |
| Barge-in / interruption       | InterruptionManager / demo_barge_in()  |
| Reliability+compliance summary | summarize_call()                      |
-------------------------------------------------------------------------

## Scenario
An insurance claims call: AI disclosure and recording consent up front,
a claim-status question, a photo of the damage, an unprompted proactive
check-in, an in-call data-erasure request, a customer talking over the
agent mid-reply, and a closing summary of how the call actually went.

## Your task
1. `run_resilient_turn()` — native-first, modular-fallback, timed and
   logged either way.
2. `redact_image_ref()` — hash+size, never raw bytes.
3. `check_erasure_request()` — keyword gate, short-circuits before any
   model call.
4. `handle_customer_turn()` — wires the erasure check, the resilient
   turn, and the log together.
5. `demo_barge_in()` — cancel mid-playback on simulated VAD.
6. `summarize_call(call_log)` — aggregate the log into one reliability +
   compliance report: turns served per path, avg/max latency per path,
   native failure count, disclosure/consent/erasure/barge-in flags.

## Why this matters
A capability that works once in a demo isn't the same as a capability
that holds up in production — this lab is where "does it work" becomes
"does it hold up," which is the actual meaning of Latency & Reliability
and Compliance. Notice what does NOT change across the failover: the
compliance gate (`disclose_ai`, consent, erasure) wraps
`handle_customer_turn()` regardless of whether the reply came from native
audio or the modular fallback — compliance is a property of the CALL,
not of which pipeline happened to answer this turn. And notice what the
summary makes visible that no single turn's log entry does: whether the
native path is actually worth its complexity for THIS call, in numbers,
not vibes.

## Files
- `compliance_policy.json` — policy-as-config: disclosure wording,
  erasure keywords, consent-refusal markers. Nothing compliance-relevant
  is hardcoded in the script.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic google-genai python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```
Runs fine with just the above (every turn uses the modular fallback). To
exercise the real native-audio-with-failover path:
```bash
export GEMINI_API_KEY=...   # ai.google.dev
```

## Stretch goals
- Per-locale disclosure wording — `disclose_ai()` currently has one
  hardcoded string regardless of region.
- Wire barge-in into an actual native session instead of the standalone
  `simulate_tts_playback()` demo — real interruption means cancelling a
  live `session.receive()` loop mid-stream, not a mocked task.
- Export `summarize_call()`'s report as JSON to a file per call, and run
  the scripted scenario 5x back to back to see the path-split and
  latency numbers stabilize (or not) against `LIVE_CONNECT_FAIL_RATE`.

## Discussion (bring back to the group)
- The erasure request mid-call: should the agent stop referencing
  anything from EARLIER in THIS call for the rest of the conversation, or
  does erasure only apply to storage going forward? Now add this lab's
  twist — if the erased turn included an image, is "we only ever stored a
  hash" enough to satisfy the request, or does the hash itself need to go
  too?
- `summarize_call()` reports latency per path, but `LIVE_CONNECT_FAIL_RATE`
  makes the native/modular split partly random per run. Is a single call's
  summary a meaningful reliability signal, or is this the same trap as
  judging a model's accuracy from one example — what would you need before
  reporting these numbers to anyone outside the room?
