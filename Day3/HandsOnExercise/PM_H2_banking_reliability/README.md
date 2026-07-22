# PM · H2 — Banking: STT Primary + Fallback for Resilience

**Track:** Banking | **Time box:** ~45 min | **Ships:** a resilient voice pipeline
**Pattern practiced:** primary/fallback provider failover with graceful degradation

## Scenario
STT providers have outages. A production voice agent that only knows how
to talk to Deepgram will go completely deaf the moment Deepgram has a bad
five minutes — and "deaf" on a phone call means dead air, which callers
hang up on immediately. Today you build the pattern that keeps the call
alive: a primary STT provider, an automatic fallback to a secondary
provider, and a last-resort graceful degradation path if both are down.

## Your task
1. `primary_stt(utterance, fail_rate=0.3)` — simulates Deepgram-like STT.
   Randomly "fails" (raises an exception) at the given rate to model a
   flaky/degraded provider; on success, sleeps a realistic latency and
   returns the transcript.
2. `fallback_stt(utterance, fail_rate=0.05)` — simulates a secondary
   provider (e.g. AssemblyAI). Lower failure rate, but usually a bit slower.
3. `robust_stt(utterance)` — tries `primary_stt` first; on failure,
   catches the exception and tries `fallback_stt`; if BOTH fail, returns a
   sentinel (`None`) rather than raising.
4. `run_turn(utterance)` — uses `robust_stt`. If it returns `None` (total
   STT failure), the agent should say something graceful ("Sorry, I'm
   having trouble hearing you — could you try again in a moment?")
   instead of crashing or going silent.
5. **Prove resilience**: run 30 simulated turns and report how many
   succeeded via primary, how many via fallback, and how many hit graceful
   degradation — then compare that to what would have happened with NO
   fallback (just primary_stt failing at its raw fail_rate).

## Why this matters
This is today's Topic 04 (reliability). The interesting engineering
decision isn't "add a try/except" — it's designing what "graceful" means
when even the fallback fails, and instrumenting the system so you can
actually prove the fallback is working (not just assume it) with real
numbers from a test run.

## Files
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
python starter.py
```
(No API key needed — this lab is entirely about the STT failover layer,
not the LLM. Feel free to wire in a real LLM call for the graceful-degradation
message if you want extra polish, but it's not required.)

## Stretch goals
- Add a circuit breaker: after 3 consecutive primary failures, skip
  `primary_stt` entirely for the next 10 turns and go straight to
  fallback — recovering only after a "cooldown."
- Track and print P50/P95 latency separately for primary-served vs.
  fallback-served turns, since a slower fallback changes your overall
  latency budget math from this morning.

## Discussion (bring back to the group)
- Your fallback provider is usually a bit slower. If primary is down for
  an extended outage, every call in that window gets worse latency, not
  just a few edge cases. How would you want that reflected in monitoring
  or alerting, so it's visible to a human, not just quietly absorbed?
