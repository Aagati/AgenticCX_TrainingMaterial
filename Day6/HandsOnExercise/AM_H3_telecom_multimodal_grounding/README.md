# AM · H3 — Telecom: Real-Time Multimodality + Tool Use & Grounding

**Track:** Telecom | **Time box:** ~40 min | **Pattern practiced:** one Live turn taking image + text together, plus function calling and Google Search grounding, on the SAME device-diagnostics scenario

## A note on this lab's simulation
No camera in the classroom, so `make_status_png()` generates a real, valid
solid-color PNG in pure stdlib (no Pillow, no binary asset file) standing
in for "customer sends a photo of their router's status light." Every
Gemini call — multimodal Live turn, function calling, grounding — is REAL
if `GEMINI_API_KEY`/`GOOGLE_API_KEY` is set, with a deterministic simulated
fallback for each independently (one missing key doesn't take down the
other two).

## Scenario
A telecom customer's internet is down. They send a photo of their router's
status light and ask what's wrong — that's real-time multimodality. The
agent needs to look up the known fix for that light color — that's tool
use. And it needs to answer a question its training data can't possibly
have ("what's the outage status right now") — that's grounding.

## Your task
1. `run_diagnostics_tool_call(user_question)` — function-calling round
   against `GET_DIAGNOSTICS_DECL`.
2. `run_grounded_search(query)` — Google Search tool round, pull citations
   from `grounding_metadata`.
3. `_run_multimodal_turn_async(image_bytes, question_text)` — ONE Live turn
   with the image sent via `send_realtime_input` and the question via
   `send_client_content`, in the same turn.

## Why this matters
Three separate capabilities, deliberately built side by side instead of in
isolation, because production agents almost never use just one:
- **Real-time multimodality** (Topic 03): the image and the question arrive
  in the SAME turn, not two round trips where you'd have to stitch the
  image analysis back into the text conversation yourself.
- **Tool use** (Topic 04, half one): the model decides WHEN to call
  `get_diagnostics` — it doesn't fire on the loyalty-discount question,
  which has nothing to look up.
- **Grounding** (Topic 04, half two): tool use answers questions about
  YOUR data (a local diagnostics DB); grounding answers questions about
  the WORLD right now. Different problem, different tool
  (`google_search`), same underlying mechanism (the model decides when it
  needs outside information and asks for it).

## Files
- `diagnostics_kb.json` — the device-diagnostics knowledge base `get_diagnostics` looks up (light color → known issue + fix).
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install google-genai python-dotenv
python starter.py
```
Runs fine with just the above (all three paths use simulation). To
exercise the real Gemini paths:
```bash
export GEMINI_API_KEY=...   # ai.google.dev
```

## Stretch goals
- Change `make_status_png`'s color to something NOT in `ROUTER_LIGHT_COLORS`
  (e.g. blue) and see how the model (or your simulated fallback) handles an
  unrecognized status light — does it guess, ask a follow-up, or say it
  doesn't know?
- Combine BOTH tools (`get_diagnostics` + `google_search`) in one
  `GenerateContentConfig` and ask a question that plausibly needs both
  ("my light is red, is there a known outage in my area right now?") — see
  which one the model reaches for first, or whether it uses both.

## Discussion (bring back to the group)
- `run_diagnostics_tool_call`'s simulated fallback does keyword matching on
  the question text — a much weaker version of what the real model does by
  actually reasoning about intent. Where in a real deployment would that
  gap between "keyword match" and "model judgment" actually bite — pick a
  question that would fool the simulated fallback but not the real model.
