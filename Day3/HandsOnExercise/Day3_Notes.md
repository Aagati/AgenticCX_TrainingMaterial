# Day 3 — Voice Pipeline: Latency, Turn-Taking, Telephony, Reliability, Compliance

Everything runs on simulated STT/TTS (`time.sleep()` modeling real vendor
latency distributions) — no microphones, no SIP trunk, no real telephony
provider. The state machines and timing math are the actual deliverable;
swapping fakes for a real LiveKit/Pipecat + Deepgram + Cartesia stack later is
a drop-in replacement, not a redesign.

Run from repo root: `.venv/Scripts/python.exe Day3_Labs/<lab>/solution.py`

---

## AM·H1 — Banking: Voice Loop + Latency Measurement
`Day3_Labs/AM_H1_banking_latency/` · instrumented STT → LLM → TTS pipeline vs. a 700ms budget

**Structure**
- `fake_stt()`/`fake_tts()` — `random.uniform(range)` + `time.sleep()`, modeling Deepgram Nova-3 (~120-220ms) / Cartesia Sonic-3 first-byte (~60-100ms) latency distributions, not fixed numbers.
- `call_llm()` — the ONLY real network call; `max_tokens=60` hard cap; system prompt bans markdown/bullets ("this gets read aloud").
- `run_turn()` — 4 `time.perf_counter()` checkpoints bracket each stage → `stt_ms`/`llm_ms`/`tts_ms`/`total_ms`, compared against `BUDGET_MS=700`. Sequential, not streaming — that's the setup for the discussion prompt.

**Test matrix**

| # | Utterance | Expected |
|---|---|---|
| 1 | "What's my account balance?" | STT ~120-220ms, TTS ~60-100ms, LLM is the largest/most variable chunk; prints `[WITHIN BUDGET]` or `[OVER BUDGET]` |
| 2 | "Can you tell me if my paycheck deposited yet?" | Same shape — confirm STT/TTS stay in their tight bands run-to-run, LLM varies more |
| 3 | "I need to report my card as lost." | Same shape — longer/more complex reply may push `llm_ms` up |

**Edge cases to cover**
- Run the same utterance 10+ times — confirm STT/TTS stay tightly bounded to their `random.uniform` ranges while LLM time swings much wider (the whole point of the lab).
- Convert to a streaming simulation (README stretch goal): have `call_llm` yield tokens progressively, start `fake_tts` on the first sentence — measure the actual savings instead of asserting it.
- Run 20 turns, report P50/P95/P99 total latency instead of eyeballing one sample (previews PM·H2's reliability stats and Day 5's eval mindset).
- A reply that blows past 60 `max_tokens` mid-sentence — does the truncated text still read naturally through `fake_tts`, or does it cut off awkwardly? Worth listening to (reading) a few truncated outputs.

---

## AM·H2 — Insurance: Tune Turn-Taking to Cut False Interruptions
`Day3_Labs/AM_H2_insurance_turntaking/` · endpointing threshold tuning, NO LLM calls, pure control flow

**Structure**
- `is_turn_complete()` — naive baseline: `silence_ms >= threshold_ms`.
- `evaluate_threshold()` — runs `test_calls.json` through ONE fixed threshold, counts false interruptions (`would_end and not is_real_end_of_turn`) vs. correct delay.
- `sweep_thresholds()` — loops 200→1000ms step 100, prints the trade-off table.
- `is_turn_complete_smart()` — the real technique: checks if the transcript's last word is in `FILLER_ENDINGS` ("um","uh","so","and",...); applies 700ms threshold if trailing on filler, else 350ms. Per-utterance adaptive threshold instead of one global number.

**Test matrix**

| # | Check | Expected |
|---|---|---|
| 1 | `sweep_thresholds()` at 450ms fixed | False interruptions remain on calls 3, 5, 7 (silence_ms ≥ 450 despite the customer trailing off) |
| 2 | `evaluate_smart()` on the same calls | Calls 3/5/7 correctly NOT flagged (transcripts end on filler/trailing words → longer threshold applied); calls 4/6/8 (genuinely complete short replies) still get short delay |
| 3 | Full sweep 200→1000ms | Monotonic-ish trade-off curve: false interruptions ↓ as threshold ↑, avg delay ↑ in lockstep |

**Edge cases to cover**
- A transcript ending on a filler word that's ALSO a legitimate complete sentence ("Yes, and" could be genuinely done or trailing) — where does the heuristic misfire?
- README's own discussion prompt: what failure mode does filler-word detection NOT catch — e.g. a customer who pauses mid-word without any trailing filler at all (a genuine "..." pause with no verbal tell). Construct a synthetic test case for this and confirm it slips through.
- Add the stretch-goal weighted single score (false-interruption cost vs. latency cost combined) — pick weights and justify the chosen threshold with a number, not a eyeballed table.
- Rising/falling intonation as a second smart signal (stretch goal) — not implemented; if added, verify it's evaluated independently from the filler-word signal, not just OR'd in blindly.

---

## AM·H3 — Telecom: Bridge the Agent to a Phone Number via SIP
`Day3_Labs/AM_H3_telecom_sip/` · call state machine: RINGING → ANSWERED → IN_PROGRESS → ENDED

**Structure**
- `simulate_incoming_call()` — Python generator yielding event dicts (`ring`/`answer`/`speech`/`dtmf`/`hangup`), standing in for a real SIP webhook stream.
- `handle_event(state, event)` — if-chain keyed on `(etype, state)`. `hangup` check is FIRST, unconditional, short-circuits from ANY state — this ordering is the answer to "what if hangup arrives mid-LLM-call."
- DTMF `"0"` is its own branch that does NOT call `call_llm` — keypad transfer-to-human bypasses the model entirely (structural guardrail, not a prompt instruction).

**Test matrix**

| # | Event sequence | Expected transitions |
|---|---|---|
| 1 | ring → answer → speech("check data usage") → speech("what's my plan?") → dtmf("0") → hangup | `RINGING → RINGING → ANSWERED → IN_PROGRESS → IN_PROGRESS → IN_PROGRESS(transfer msg, NO LLM call) → ENDED` |

**Edge cases to cover**
- `hangup` arriving WHILE waiting on an LLM response (README's own discussion question) — the reference solution doesn't actually model concurrent/in-flight calls (it's synchronous), so this is a good "what would you need to add" whiteboard exercise, not just a code test.
- `speech` event arriving in `RINGING` state (before `answer`) — falls through to the catch-all `"(unhandled event ... in state ...)"` print — confirm that's graceful, not a crash.
- DTMF digit other than `"0"` (e.g. "5") — no branch handles it, also falls to the unhandled catch-all — is silently ignoring non-zero DTMF the right call, or should it echo back "invalid option"?
- Call that never gets `answer` (stretch goal: `NO_ANSWER` terminal state after N events) — not implemented; current state machine would just sit in `RINGING` forever if `answer` never arrives.
- Call-recording consent gate BEFORE any `speech` reaches the LLM (stretch goal, previews PM·H3) — not implemented here; PM·H3 is where this actually gets built.

---

## PM·H1 — Insurance: Voice Agent That Answers a Claim-Status Call
`Day3_Labs/PM_H1_insurance_voiceagent/` · full pipeline: AM·H1 + AM·H2 + AM·H3 fused into one `VoiceAgent` class + tool-calling

**Structure**
- `run_llm_turn()` — same `next()`-based single-tool-check + one-followup shape as every prior tool loop; returns `(text, num_llm_calls)` so the call count feeds directly into the latency printout.
- `run_turn()` — gates on `is_turn_complete(silence_ms)` (hardcoded 400ms, no smart version — README explicitly says don't over-engineer here) before timing STT→LLM→TTS exactly like AM·H1.
- `VoiceAgent.handle_event()` — same transition shape as AM·H3's `handle_event`, but now a method holding `self.state`; the `speech` branch calls `run_turn()` instead of a bare `call_llm()`.

**Test matrix**

| # | Event sequence | Expected |
|---|---|---|
| 1 | ring → answer → speech("check status of claim CLM-3391?") → speech("Great, thank you!") → hangup | Greeting printed on answer. Turn 1: `get_claim_status` tool fires, `num_llm_calls=2`, visibly higher `LLM ms` in the printout. Turn 2: no tool needed, `num_llm_calls=1`, noticeably lower `LLM ms`. |

**Edge cases to cover**
- Claim id that doesn't exist in `claims_data.json` — `get_claim_status` returns `{"error": "claim not found"}` — confirm the follow-up LLM call produces a sensible spoken reply instead of reading the raw error dict aloud.
- Add a 2nd tool (README stretch goal, e.g. `get_policy_summary`) — confirm the model picks the right tool based on what was actually asked, not just always the first-defined one.
- Track cumulative call duration + tool-call count across the whole call, print a summary at `ENDED` (stretch goal) — not implemented; good exercise to bolt onto the existing `VoiceAgent` class.
- README's own discussion prompt: the tool-call turn roughly DOUBLES LLM latency (2 round-trips). Would you want the agent to say "Let me pull that up for you..." during the wait rather than dead air? What would that take to build — worth sketching even without implementing.

---

## PM·H2 — Banking: STT Primary + Fallback for Resilience
`Day3_Labs/PM_H2_banking_reliability/` · primary/fallback provider failover, NO LLM calls

**Structure**
- `primary_stt()`/`fallback_stt()` — each independently rolls `random.random() < fail_rate` to raise `STTFailure`; different fail rates (0.3 vs 0.05) and different latency ranges (fallback slower) — models a degraded-but-not-dead secondary.
- `robust_stt()` — nested try/except: primary fails → fallback → fallback also fails → return `None` sentinel (not another exception), so callers just do an `is None` check.
- `prove_resilience()` — runs 30 turns, tallies outcomes, then computes what the RAW `PRIMARY_FAIL_RATE` alone would've produced for comparison — quantifying the fallback's value with real numbers instead of asserting it qualitatively.

**Test matrix**

| # | Run | Expected (statistical, not exact — reseed for exact repro) |
|---|---|---|
| 1 | `prove_resilience(30)` | ~70% served primary, ~28% fallback, ~1-2% genuinely degraded (both fail) — vs. ~30% degraded with NO fallback at all |

**Edge cases to cover**
- Set `PRIMARY_FAIL_RATE` to something extreme (e.g. 0.9) to visibly stress the fallback path — confirm `robust_stt` still degrades gracefully rather than raising.
- Circuit breaker (README stretch goal): after 3 consecutive primary failures, skip primary for the next 10 turns, recover after cooldown — not implemented; a good "add reliability engineering on top of a working failover" exercise.
- Separate P50/P95 latency for primary-served vs. fallback-served turns (stretch goal) — not implemented; matters because a slower fallback changes the overall latency budget math from AM·H1, and that's currently invisible in the aggregate stats.
- README's own discussion prompt: an EXTENDED primary outage degrades EVERY call in that window, not just a random few — does your reporting surface that as a visible pattern to a human (alerting), or does `prove_resilience`'s per-run summary quietly absorb it into a "28% fallback" statistic that looks routine?

---

## PM·H3 — Telecom: AI Disclosure + Consent + Recording Handling
`Day3_Labs/PM_H3_telecom_compliance/` · mandatory disclosure/consent gate BEFORE conversation logic runs

**Structure**
- `call_log` — plain list of event dicts, passed by reference and mutated in place (`.append()`) through the whole flow — one audit-trail object threaded end to end.
- `compliant_call_flow()` — boolean flag `pending_consent_prompt` (simpler than AM·H3's full state-string machine, since this lab only cares about ordering: disclosure → consent → speech).
- Critical structural point: `disclose_ai()` and `request_recording_consent()` fire unconditionally on the `answer` event, BEFORE the loop can reach a `speech` branch that hits the LLM — enforced by code position, not a system-prompt instruction.
- `check_erasure_request()` — plain keyword-list substring check, deliberately NOT an LLM call — intercepts and short-circuits `handle_speech()` before `call_llm()` runs.

**Test matrix**

| # | Event sequence | Expected `call_log` |
|---|---|---|
| 1 | answer → consent_response("Sure, that's fine.") → speech("check data usage") → speech("delete my data from this call?") → speech("thanks, that's all") → hangup | `disclosure_given` → `recording_consent(granted=True)` → `turn`(data usage) → `erasure_requested` (NOT a normal `turn` entry) → `turn`("thanks, that's all") — 4 distinct event types, in order |

**Edge cases to cover**
- Caller REFUSES recording consent ("No, please don't record this") — `granted=False`; confirm the call CONTINUES unrecorded rather than being blocked entirely (README is explicit about this — refusal ≠ call termination).
- Erasure request phrased outside the hardcoded `ERASURE_KEYWORDS` list (e.g. "please get rid of everything you have on me") — the substring check will MISS this; good live demo of why a keyword list alone under-catches, tying back to Day 4's guardrail-precision lessons.
- Erasure request mid-call — README's own discussion question: should the agent stop referencing anything from EARLIER in the SAME call for the rest of the conversation, or does erasure only apply to storage going forward? Not resolved in the reference solution — worth a group discussion, not just a code fix.
- Per-locale disclosure wording (stretch goal, US vs EU caller) — not implemented; `disclose_ai()` currently has one hardcoded string regardless of region.
- `consent_response` event arriving when `pending_consent_prompt` is already `False` (e.g. a duplicate event) — confirm it's silently ignored rather than double-logging.
