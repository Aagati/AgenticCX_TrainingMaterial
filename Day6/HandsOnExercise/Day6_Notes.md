# Day 6 — Advanced Voice & Multimodal CX with Google Gemini

Every Gemini call in every lab is REAL if `GEMINI_API_KEY`/`GOOGLE_API_KEY`
is set, and falls back to a deterministic simulation otherwise — same
"real-if-key" contract Day 3 used for Deepgram. Claude calls (where
present) are always real; every lab in this repo assumes
`ANTHROPIC_API_KEY` is configured.

Run from repo root: `.venv/Scripts/python.exe Day6/HandsOnExercise/<lab>/solution.py`

**Facilitator note — teaching PM-only:** the three PM labs carry every
concept the three AM labs teach, with no dependency on the AM labs having
run. PM_H1 does the heaviest lifting here — it fuses BOTH of AM_H1's paths
(not just native), AM_H2's affect/proactive config, and AM_H3's tools +
grounding + multimodal input, then closes with `demo_am_recap()`, a
standalone rerun of AM_H1's timed comparison and AM_H2's on/off + proactive
demos. PM_H2 stands on its own for tooling/actions/Gemini-vs-modular.
PM_H3 reuses PM_H1's reconnect logic, AM_H1's modular path (as a failover
target), and AM_H2's proactive-turn attribution for its own compliance
gate. Running `solution.py` in all three PM folders, in order, covers all
9 of today's major topics plus the platform-landscape discussion — a
viable 4-hour evening-only session.

---

## AM·H1 — Banking: Pipeline vs. Native Audio
`Day6/HandsOnExercise/AM_H1_banking_native_audio/` · 3-hop modular pipeline vs. 1-hop native-audio Live session, same utterance, both timed

**Structure**
- `run_modular_turn()` — `fake_stt` → real streamed Claude call → `fake_tts`, same shape as Day 3's AM_H1, summed into `total_ms`.
- `_run_native_turn_async()` — one Gemini Live session, text turn in, audio deltas out; timestamps time-to-first-audio-byte, not full completion.
- `run_native_turn()` — real-if-key dispatcher; simulated fallback is a single `random.uniform(250,400)ms` draw.
- `compare_turn()` — runs both, prints the delta.

**Test matrix**

| # | Utterance | Expected |
|---|---|---|
| 1-3 | The 3 banking utterances | Modular total = sum of 3 draws + real Claude latency; native total = 1 draw (sim) or 1 real round trip. Native usually wins on total, and ALWAYS wins on hop count (1 vs 3). |

**Edge cases to cover**
- Run with no `GEMINI_API_KEY` — confirm native path is clearly labeled "simulated" in the printout, never silently presented as real.
- Force a bad `NATIVE_AUDIO_MODEL` id (real key set) — confirm the except branch in `run_native_turn` catches it and falls back rather than crashing.
- Stretch goal (reused connection across all 3 turns) — not implemented; good live demo of whether the FIRST turn's handshake cost disappears for turns 2-3.

---

## AM·H2 — Insurance: Affective Dialogue & Proactive Audio
`Day6/HandsOnExercise/AM_H2_insurance_affective_proactive/` · `enable_affective_dialog` + `proactivity.proactive_audio`, both against a labeled transcript fixture

**Structure**
- `detect_affect_cues()` — text-only stand-in for tone/prosody (distress keywords, exclamation count, ALL-CAPS words) — a heuristic, explicitly NOT how the real feature works.
- `evaluate_affect_detection()` — scores the heuristic against `call_transcripts.json`'s 8 labeled calls.
- `compare_affect_modes()` — same utterance, affect config on vs. off.
- `_listen_for_proactive_async()` — sends a turn, drains the reply, then goes quiet and watches for an unprompted message within `PROACTIVE_TIMEOUT_S`.

**Test matrix**

| # | Check | Expected |
|---|---|---|
| 1 | `evaluate_affect_detection()` | 8/8 — the heuristic was built directly against the fixture |
| 2 | `compare_affect_modes` on a distressed transcript | Visibly different reply tone on vs. off (simulated: two different hardcoded strings; real: qualitatively similar difference, model-dependent wording) |
| 3 | `listen_for_proactive_checkin` × 10+ runs per affect bucket | Distressed ~70% proactive (simulated), neutral/positive ~15% — a statistical split, not a single-sample guarantee |

**Edge cases to cover**
- A transcript that's calm in WORDS but would read as distressed in TONE if spoken ("I'm fine, really, it's fine.") — confirm the text-only heuristic misses it; that gap is the discussion prompt.
- No `GEMINI_API_KEY` — confirm BOTH affective-dialogue and proactive-audio calls fall back independently (one missing key doesn't crash the other).

---

## AM·H3 — Telecom: Real-Time Multimodality + Tool Use & Grounding
`Day6/HandsOnExercise/AM_H3_telecom_multimodal_grounding/` · one Live turn with image+text, plus function calling and Google Search grounding, no Live API needed for the latter two

**Structure**
- `make_status_png()` — pure-stdlib PNG encoder (no Pillow), solid-color image standing in for a photo of a router status light.
- `run_diagnostics_tool_call()` — function-calling round against `GET_DIAGNOSTICS_DECL`.
- `run_grounded_search()` — `google_search` tool round, pulls citations from `grounding_metadata`.
- `_run_multimodal_turn_async()` — image via `send_realtime_input`, question via `send_client_content`, SAME turn.

**Test matrix**

| # | Input | Expected |
|---|---|---|
| 1-3 | red / amber / green status PNG + question | Diagnosis matches `DIAGNOSTICS_DB` for that color, real or simulated |
| 4 | "My router light is red..." | `tool_called=True`, `light_color="red"` |
| 5 | "Is my plan eligible for a discount?" | `tool_called=False` — no light color mentioned, nothing to look up |
| 6 | Grounded search query | Real: non-empty `citations`. Simulated: always empty — that emptiness IS the signal a fallback can't fabricate real grounding |

**Edge cases to cover**
- A light color NOT in `ROUTER_LIGHT_COLORS` (e.g. blue) — `get_diagnostics` returns the `"unknown"` catch-all; confirm the model (or fallback) handles it gracefully rather than guessing confidently.
- Combine both tools (`get_diagnostics` + `google_search`) in one `GenerateContentConfig` (stretch goal) — not implemented; worth testing live whether the model reaches for one, the other, or both.

---

## PM·H1 — Retail: Production Architecture
`Day6/HandsOnExercise/PM_H1_retail_production_architecture/` · AM_H1's BOTH paths (modular Claude + native Gemini) + AM_H2 + AM_H3 fused into `RetailSupportSession`, routed per-turn, plus session resumption + structured logging + a standalone AM recap

**This is the lab to teach if the session is PM-only** (see facilitator
note at the top of this file) — `demo_am_recap()` reproduces AM_H1's timed
modular-vs-native comparison and AM_H2's affect-on/off + proactive-checkin
behavior with no dependency on the AM labs having run.

**Structure**
- `run_modular_turn()` — AM_H1's exact `fake_stt -> real streamed Claude -> fake_tts` shape, unchanged, reused as the cost-routed path.
- `_needs_native()` — routing decision: image present, an `ORDER_DB` order id mentioned, or a `GROUNDING_HINT_WORDS` match → native; otherwise → modular.
- `_build_config(enable_affect, enable_proactive)` — one `LiveConnectConfig` combining native audio, both AM_H3 tools, and `SessionResumptionConfig`; affect/proactivity toggleable (default True for the main session, toggled by the recap).
- `_run_turn_async()` — handles multimodal send, `tool_call` messages (execute + `send_tool_response`), and `session_resumption_update` capture, all in one receive loop.
- `simulate_dropped_connection_and_reconnect()` — logs the drop/reconnect sequence; the actual "reconnect" is just the next `send_turn()` call reusing the saved handle.
- `_run_bare_turn_async()` / `_listen_for_proactive_async()` — no-tool, toggleable-affect variants of the native turn, used only by `demo_am_recap()`.

**Test matrix**

| # | Sequence | Expected log |
|---|---|---|
| 1 | order-status turn → photo-return turn → plain-FAQ turn → "delay...today" turn → simulated drop → order-status follow-up | Turns 1, 2, 4, 5 route `"native"` (`tool_call` fires on 1 and 5; turn 4 exercises the `google_search` tool); turn 3 routes `"modular"` and is answered by a REAL Claude call (`real=True`) regardless of Gemini key status; `connection_dropped` → `reconnect_attempt` → `reconnected` between turns 4 and 5, `using_saved_handle=True` ONLY if a real native session returned a resumption update at least once |
| 2 | `demo_am_recap()` | Prints a timed modular-vs-native comparison for the same utterance (recap 1/3), an affect-off vs. affect-on reply pair on a distressed message (recap 2/3), and a proactive-checkin bool (recap 3/3) — all real-if-key / simulated-fallback like everything else this day |

**Edge cases to cover**
- Full Gemini simulation (no key) — confirm `using_saved_handle` stays `False` through the whole reconnect sequence, and that this is the CORRECT behavior (you can't resume a session that was never really opened), not a bug. The modular turn is UNAFFECTED by Gemini key status — it's always real.
- Force `_run_turn_async` to raise (stretch goal: break the model id temporarily) — confirm `send_turn`'s except branch logs `turn_failed` and still returns a usable simulated reply, and that this only affects `route="native"` turns.
- A turn that mentions an order id AND has no image AND isn't really about that order (e.g. "is ORD-4471 the same numbering scheme you use for returns?") — `_needs_native` routes it native anyway on the substring match; worth asking whether that's the right call or a routing false positive.
- `demo_am_recap()`'s affect-off/affect-on pair, when simulated, are two HARDCODED strings, not a real toggle — with a real key, confirm the two Gemini calls actually differ in tone, not just in this lab's canned fallback text.

---

## PM·H2 — Banking: Tooling & Actions via LangGraph
`Day6/HandsOnExercise/PM_H2_banking_tooling_langgraph/` · one `StateGraph`, instantiated with a Claude node and a Gemini node

**Structure**
- `build_action_graph(llm_with_tools)` — 2-node graph (`agent` → conditional → `execute`/`END`), model-agnostic.
- `make_agent_node()` — decides tool need; gates `freeze_card` behind `state["confirmed"]`.
- `make_execute_node()` — runs the tool, gets the natural-language follow-up.
- `SimulatedGeminiModel` — duck-types `.invoke(messages)` so the Gemini graph runs identically shaped whether real or simulated.

**Test matrix**

| # | Sequence | Expected |
|---|---|---|
| 1 | "What's my balance?" | One agent-node pass, `get_account_info` tool call, reply with balance/deposit info |
| 2 | "I lost my card" (confirmed=False) | Stops at agent node, confirmation-request reply, `card_status` still `"active"` |
| 3 | Same message, confirmed=True (fresh invoke) | Reaches execute node, `card_status` flips to `"frozen"` |

Run both `claude_graph` and `gemini_graph` through this sequence — the
STATE MACHINE behavior (which node fires, when) must be IDENTICAL between
the two; only wording should differ.

**Edge cases to cover**
- No `GEMINI_API_KEY` — confirm `SimulatedGeminiModel` still triggers the SAME 3-step sequence (tool call → confirm gate → execute) via its keyword matching, not just a generic reply.
- `ACCOUNT["card_status"]` must be reset to `"active"` between the two `demo()` calls (already done in `__main__`) — otherwise the Gemini demo's freeze-card step has nothing to freeze.

---

## PM·H3 — Insurance: Latency & Reliability + Compliance
`Day6/HandsOnExercise/PM_H3_insurance_reliability_compliance/` · the day's capstone fusion — native/modular failover, proactive-audio attribution, multimodal redaction, disclosure/consent/erasure, barge-in

**Structure**
- `run_resilient_turn()` — native-first (with a simulated `LIVE_CONNECT_FAIL_RATE=0.25` unreachable draw even when a key IS set), modular fallback (AM_H1's shape) on any failure.
- `redact_image_ref()` — hash+size only, never raw bytes.
- `handle_customer_turn()` — erasure check FIRST (short-circuits before any model call), then the resilient turn, all logged.
- `demo_barge_in()` — Day 3 AM_H2's `InterruptionManager`, unchanged.

**Test matrix**

| # | Sequence | Expected `call_log` |
|---|---|---|
| 1 | disclose → consent → claim-status turn → photo turn → proactive check-in → erasure request → barge-in | `disclosure_given` → `consent_requested` → `recording_consent(granted=True)` → (`turn_served` path native or modular) ×2, one with an `image` hash entry → `agent_turn(agent_initiated=True)` (the ONLY one) → `erasure_requested(transcript="[REDACTED]")` with NO following `turn_served` → `barge_in(cancelled=True)` |

**Edge cases to cover**
- Erasure phrased outside `ERASURE_KEYWORDS` (e.g. "please get rid of everything you have on me") — the substring check misses it, same under-catch lesson Day 3's PM·H3 flagged, now recurring on purpose.
- No `GEMINI_API_KEY` — confirm EVERY `turn_served` entry shows `path="modular"`, never `"native"` — the failover isn't optional when there's nothing to fail over FROM.
- Caller refuses recording consent ("No, don't record this") — `granted=False`; confirm the call continues unrecorded rather than terminating (same explicit Day 3 PM·H3 behavior).
