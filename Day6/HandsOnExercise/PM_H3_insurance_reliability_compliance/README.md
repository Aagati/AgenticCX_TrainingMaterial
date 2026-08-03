# PM · H3 — Insurance: Latency & Reliability + Compliance

**Track:** Insurance | **Time box:** ~45 min | **Pattern practiced:** every prior lab today, closed out with a failover path, an attribution rule, and a compliance gate

## How this compounds on the whole day
This is the day's capstone lab, same role Day 3's PM·H1 played:
- **AM_H1** — the "modular vs. native" comparison stops being a benchmark
  and becomes a real failover target: `run_resilient_turn()` tries native
  audio first, and drops to the 3-hop modular pipeline on ANY failure.
- **AM_H2** — proactive audio's unprompted turn gets a distinct
  `agent_initiated=True` log tag, because "who spoke first" is now a
  compliance fact, not a UX detail.
- **AM_H3** — an attached image is logged as a redacted hash+size
  reference, never raw bytes.
- **PM_H1** — the reconnect discipline from session resumption, applied
  here to a HARDER failure: not a drop-and-resume, a genuinely unreachable
  Live API, where reconnecting isn't an option and failing over is.
- **Day 3's PM·H3** — the disclosure → consent → erasure gate shape,
  unchanged in structure, insurance-flavored.

New this lab: **interruption/barge-in** (Day 3's AM·H2 `InterruptionManager`,
reused as-is — cutting off mid-playback is a reliability concern no matter
whose Live API is under the hood).

## Scenario
An insurance claims call: AI disclosure and recording consent up front,
a claim-status question, a photo of the damage, an unprompted proactive
check-in, an in-call data-erasure request, and a customer talking over the
agent mid-reply.

## Your task
1. `run_resilient_turn()` — native-first, modular-fallback, logged either way.
2. `redact_image_ref()` — hash+size, never raw bytes.
3. `check_erasure_request()` — keyword gate, short-circuits before any model call.
4. `handle_customer_turn()` — wires the erasure check, the resilient turn, and the log together.
5. `demo_barge_in()` — cancel mid-playback on simulated VAD.

## Why this matters
Every AM lab today built one capability real enough to demo. None of them
alone survives a bad network day, a regulator's audit request, or a
customer talking over the agent — this lab is where "does it work in the
lab" becomes "does it hold up in production," which is the actual meaning
of today's Latency & Reliability and Compliance topics. Notice what does
NOT change across the failover: the compliance gate (`disclose_ai`,
consent, erasure) wraps `handle_customer_turn()` regardless of whether the
reply came from native audio or the modular fallback — compliance is a
property of the CALL, not of which pipeline happened to answer this turn.

## Files
- `compliance_policy.json` — policy-as-config (Day 4's term for it): disclosure wording, erasure keywords, consent-refusal markers. Nothing compliance-relevant is hardcoded in the script.
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
- Track path (`native` vs `modular`) per turn across a 20-turn synthetic
  call and report the split — same reliability-quantification move Day
  3's PM·H2 made for STT primary/fallback.
- Per-locale disclosure wording (Day 3 PM·H3 left this as a stretch goal
  too, still not implemented anywhere in this repo) — `disclose_ai()`
  currently has one hardcoded string regardless of region.

## Discussion (bring back to the group)
- The erasure request mid-call (same open question Day 3's PM·H3 left
  unresolved): should the agent stop referencing anything from EARLIER in
  THIS call for the rest of the conversation, or does erasure only apply
  to storage going forward? Now add today's twist — if the erased turn
  included an image, is "we only ever stored a hash" enough to satisfy the
  request, or does the hash itself need to go too?
