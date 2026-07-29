# AM · H3 — Telecom: Bridge the Agent to a Phone Number via SIP

**Track:** Telecom | **Time box:** ~20 min | **Pattern practiced:** call state machine — ringing → answered → in-progress → ended, with DTMF handling

## A note on this lab's simulation
No real SIP trunk or phone number here — `simulate_incoming_call()`
generates a sequence of call events (ringing, answered, speech, DTMF
digits, hangup) the way a real SIP/telephony provider (Twilio, or
LiveKit's native SIP support) would deliver them to your application via
webhooks or an event stream. **The state machine you build today is
exactly what sits behind that event stream in production** — only the
event source is a Python generator instead of a real phone network.

Call events (including "customer speech") stay simulated either way — but
for a live demo, everything the AGENT says (greeting, LLM replies, the
transfer line) is synthesized through a **real Deepgram Aura TTS stream**
when `DEEPGRAM_API_KEY` is set, via the given `speak(label, text)` helper,
and saved as WAVs under `sample_audio/`. No key? `speak()` falls back to
text-only, silently — your `handle_event()` logic never needs to branch on
which path it's on, same seam pattern as AM·H1's `stt()`/`tts()`.

## Scenario
Bridging a voice agent to an actual phone number means handling a very
different lifecycle than a web chat: calls ring, get answered (or not),
run for a while, may receive DTMF (keypad) input, and eventually end —
and your code needs to react correctly to each transition, including ones
that don't go how you'd like (call never answered, caller hangs up mid-turn).

## Your task
Build a call state machine with states `RINGING`, `ANSWERED`,
`IN_PROGRESS`, `ENDED`, and:
1. `handle_event(call_state, event)` — given the current state and an
   incoming event (`{"type": "answer"}`, `{"type": "speech", "text": "..."}`,
   `{"type": "dtmf", "digit": "1"}`, `{"type": "hangup"}`), return the new
   state and any action to take (e.g., on `answer`, transition to
   `ANSWERED` and play a greeting; on `speech` while `IN_PROGRESS`, call
   the LLM for a reply).
2. Wire `speech` events through this morning's H1 pipeline pattern
   (STT → LLM → TTS conceptually — here just LLM, since STT/TTS are
   simulated) to generate a spoken reply.
3. Handle `dtmf` — e.g., pressing `0` during the call should transition
   toward a "transfer to human" action rather than going through the LLM.
4. Run `simulate_incoming_call()` (provided) through your state machine
   end to end and print the full call transcript with state transitions.

## Why this matters
This is today's Topic 04 (orchestration) applied to the telephony leg
specifically: a voice agent framework's SIP integration (LiveKit's native
SIP support, or a Twilio bridge in front of Pipecat) hands you exactly this
kind of event stream — ringing, answered, media, DTMF, hangup — and your
application logic needs a real state machine to handle it correctly, not
just a "handle the next thing that happens" script.

## Files
- `starter.py` — scaffold with TODOs, includes `simulate_incoming_call()`.
- `solution.py` — reference solution.
- `sample_audio/` — generated at runtime; real Deepgram TTS clips of the
  agent's lines (greeting, replies, transfer message) when a Deepgram key
  is set. Empty / absent otherwise — nothing to commit, nothing required.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```
Optional, for real agent-side audio instead of text-only:
```bash
pip install deepgram-sdk
export DEEPGRAM_API_KEY=...
```

## Stretch goals
- Add a `voicemail` path: if `answer` never arrives within N simulated
  events, transition to a `NO_ANSWER` terminal state instead of hanging
  indefinitely.
- Add call recording consent as a required step right after `ANSWERED`
  and before allowing any `speech` event to reach the LLM — this previews
  this afternoon's Topic 06 (Compliance) and PM·H3.

## Discussion (bring back to the group)
- What should happen to an in-progress LLM call if a `hangup` event
  arrives while you're waiting on a response? What's the risk of not
  handling that case explicitly?
