# PM · H1 — Retail: Production Architecture

**Track:** Retail | **Time box:** ~45 min | **Pattern practiced:** a modular Claude pipeline + a native Gemini Live session (with affective dialogue, proactive audio, tool calling, and grounding) fused into one `RetailSupportSession` class, routed per-turn, then hardened with session resumption + a structured audit log

## What this lab is about
One class, several capabilities working together on one retail-support
scenario:
- **Two paths, routed per turn** — `run_modular_turn()` is the
  `fake_stt -> real streamed Claude -> fake_tts` shape, and
  `_run_turn_async()` is the native Gemini Live session. `_needs_native()`
  routes each turn to whichever one it actually needs.
- **Affective dialogue + proactive audio** — `enable_affective_dialog` and
  `proactivity.proactive_audio` are on by default in `_build_config()`,
  for the native path.
- **Tool calling + grounding + multimodal input** — `get_order_status` is
  a real function-calling tool, `google_search` is wired in for grounding,
  and the return-request turn attaches a real image via
  `send_realtime_input`.

New this lab: **production architecture** — a dropped connection shouldn't
mean restarting the conversation, and every meaningful event needs to land
in a structured log a human (or an eval pipeline) can read later.

**Why Claude/the Anthropic SDK shows up here at all:** production
architecture isn't just "keep the Gemini session alive" — it's also
"don't put every request through the most expensive, most complex path
available." A plain FAQ turn ("what's your return window?") doesn't need a
native-audio session with two tools and grounding bound to it. This lab
routes that kind of turn to the modular Claude pipeline instead, and
reserves the native Gemini session for turns that actually need its
multimodal input or its order-lookup tool. That's a genuine
architecture-level cost/complexity decision, distinct from PM·H3's
reliability-driven failover later today — same two functions
(`run_modular_turn` / native session), different trigger:

| | Trigger | Decided | Topic |
|---|---|---|---|
| **PM_H1 (this lab)** | request doesn't need native's capabilities | upfront, before anything runs | production architecture |
| **PM_H3 (this afternoon)** | native is unreachable | after a failure | reliability |

**Where the managed platforms sit** (Gemini Enterprise Agent Platform /
Customer Engagement Suite / CX Agent Studio, today's named platforms):
everything in this lab talks to the Live API directly — you own the
session, the routing decision, the reconnect logic, the audit trail.
Google also ships managed layers on top of the same models: **Gemini
Enterprise Agent Platform** (agent orchestration + deployment),
**Customer Engagement Suite** (a packaged CX product built on it), and
**CX Agent Studio** (its no/low-code authoring surface). None of them
change what this lab does — they change who operates the session
lifecycle and how much of this lab's plumbing you'd get for free in
production instead of building by hand.

## Scenario
A retail customer calls support: checks an order status (needs the tool →
native), sends a photo of a damaged item (needs multimodal → native), asks
an unrelated policy question while on hold (needs neither → modular), asks
about a live shipping delay (needs grounding → native), then the
connection drops mid-conversation and reconnects for one more
order-status check (native again, to actually exercise resumption).
`demo_capability_recap()` then runs three short standalone demos
recapping the pipeline-vs-native timing and the affect/proactive
behavior.

## Your task
1. `call_llm_streaming()` / `run_modular_turn()` — a real streamed
   Claude call.
2. `_build_config()` — assemble the fused `LiveConnectConfig` for the
   native path, with affect/proactivity toggleable.
3. `_run_turn_async()` — open the native session, handle the multimodal
   send, handle `tool_call` messages, handle `session_resumption_update`,
   collect the reply.
4. `_needs_native()` — the routing decision (image, order id, or a
   grounding-hint word).
5. `send_turn()` — route to modular or native, log which, return the reply.
6. `simulate_dropped_connection_and_reconnect()` — log the drop/reconnect
   sequence.
7. `_run_bare_turn_async()` / `_listen_for_proactive_async()` — the two
   helpers `demo_capability_recap()` uses to reproduce the affect and
   proactive-audio demos standalone (fully given in `__main__`, but the
   helpers themselves are TODOs — same logic as `_run_turn_async` and the
   proactive silence-gap listen, just without tool/multimodal handling).

## Why this matters
Learning one capability in isolation is the right way to LEARN it and the
wrong way to SHIP it — a real production agent runs all of them in the
same session, at the same time, against the same customer, AND has to
decide when NOT to reach for the heaviest tool available. Session
resumption matters because a Live API session is a stateful websocket,
not a stateless request — reliability here isn't solved for one stage of
a pipeline, it's a property of the WHOLE session, solved by carrying a
server-issued handle across the gap instead of re-establishing context
from scratch.

## Files
- `order_data.json` — the order-status knowledge base `get_order_status` looks up.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic google-genai python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```
Runs fine with just the above — the modular route is always a real Claude
call, the native route falls back to simulation without a Gemini key. To
exercise the real native path end to end:
```bash
export GEMINI_API_KEY=...   # ai.google.dev
```

## Optional: real duplex voice
Every turn above sends TEXT — even the native route only gets real audio
BACK, never real mic input. `RetailSupportSession.run_live_voice_demo()` is
a separate, opt-in flow that opens a real mic-in/speaker-out loop against
the same session config (tools, resumption, affect/proactivity included),
and additionally handles `interrupted` (barge-in) and `tool_call` messages
arriving mid-audio-stream. Not part of the scripted `__main__` turns, so
the default lab still runs on a laptop with no mic. Try it with:
```bash
pip install pyaudio   # needs system portaudio; optional, only for --voice
python solution.py --voice
```

## Stretch goals
- Print a session summary at the end: total turns, split by route
  (modular vs. native), tool calls made, whether a resumption handle was
  ever captured.
- Force `_run_turn_async` to raise partway through (e.g. temporarily break
  `MULTIMODAL_LIVE_MODEL`'s name) and confirm `send_turn`'s except branch
  logs `turn_failed` AND still returns a usable simulated reply — the
  session should degrade, not crash.

## Discussion (bring back to the group)
- `_needs_native()` is a simple heuristic (image present, an order id
  mentioned, or a grounding-hint word like "today"/"current"). What's a
  turn it would route WRONG — either sending a plain-FAQ-shaped question
  to the expensive native session, or sending a question that actually
  needed grounding/tools to the cheap modular one?
- `session_resumption_update` only arrives from a REAL native session — in
  full Gemini simulation, `using_saved_handle` stays `False` through the
  whole reconnect sequence. Is that a bug in this lab, or the correct
  behavior?
