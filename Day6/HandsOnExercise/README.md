# Day 6 — Advanced Voice & Multimodal CX with Google Gemini

Hands-on only — no separate Applied Lab notebook for this day (see
`../../contents.md` for why). Six labs: AM_H1-H3 build individual Gemini
Live API capabilities in isolation; PM_H1-H3 compound those into
production-shaped systems, the same "build it, then fuse it" arc Day 3
used for the voice pipeline.

Every real Gemini call in every lab follows the same contract the rest of
this repo uses for vendor SDKs (Day 3's Deepgram calls, Day 5's Langfuse
traces): **real if a key is configured, deterministic simulated fallback
otherwise** — so every lab runs for every student, key or no key.

Run from repo root: `.venv/Scripts/python.exe Day6/HandsOnExercise/<lab>/solution.py`

**Teaching PM-only (e.g. a 4-hour evening-only slot):** the three PM labs
carry every AM concept — PM_H1 fuses BOTH of AM_H1's paths (not just
native audio) + AM_H2 + AM_H3, and closes with `demo_am_recap()`, a
standalone rerun of AM_H1's timed comparison and AM_H2's on/off +
proactive demos. See the facilitator note at the top of `Day6_Notes.md`
for the full breakdown.

---

## Pre-Lunch — Concepts

| Folder | Lab | Industry | Topics covered |
|---|---|---|---|
| `AM_H1_banking_native_audio` | Pipeline vs. Native Audio | Banking | Topic 01 (pipeline → native audio), Topic 06 (Gemini vs. the modular stack) |
| `AM_H2_insurance_affective_proactive` | Affective Dialogue & Proactive Audio | Insurance | Topic 02 |
| `AM_H3_telecom_multimodal_grounding` | Real-Time Multimodality + Tool Use & Grounding | Telecom | Topic 03, Topic 04 |

## Post-Lunch — Production

| Folder | Lab | Industry | Topics covered | Compounds on |
|---|---|---|---|---|
| `PM_H1_retail_production_architecture` | Production Architecture | Retail | Topic 05 (production architecture) | AM_H1's BOTH paths (modular Claude + native Gemini, routed per-turn) + AM_H2 + AM_H3 |
| `PM_H2_banking_tooling_langgraph` | Tooling & Actions via LangGraph | Banking | Topic 07 (tooling & actions), Topic 06 made concrete in code | AM_H3's tool-calling shape |
| `PM_H3_insurance_reliability_compliance` | Latency & Reliability + Compliance | Insurance | Topic 08 (latency & reliability), Topic 09 (compliance) | PM_H1's reconnect logic, AM_H1 as fallback target, AM_H2's proactive-audio attribution, AM_H3's redaction |

**Where "Gemini Enterprise Agent Platform / Customer Engagement Suite / CX
Agent Studio" (the day's named platforms) fit in:** they're managed,
console-driven layers built on top of the same Live API these labs script
directly — no pip-installable SDK surface to hand-on. Covered as
discussion material in `AM_H1`'s README rather than as a separate lab, the
same treatment Day 3 gave "build vs. buy."

---

## Supplementary data files

Every lab that looks something up externalizes what it looks up into its
own JSON fixture, instead of hardcoding it in the script — same
policy/knowledge-base-as-config convention Day 4/5 used:

| Lab | File | What it holds |
|---|---|---|
| `AM_H2_insurance_affective_proactive` | `call_transcripts.json` | 8 labeled sample calls for testing the affect heuristic |
| `AM_H3_telecom_multimodal_grounding` | `diagnostics_kb.json` | router-light-color → known issue/fix knowledge base |
| `PM_H1_retail_production_architecture` | `order_data.json` | order-status knowledge base |
| `PM_H2_banking_tooling_langgraph` | `account_ledger.json` | mock account fixture (same shape as Day 3's) |
| `PM_H3_insurance_reliability_compliance` | `compliance_policy.json` | disclosure wording, erasure keywords, consent-refusal markers |

**No `sample_audio/` folders this day, unlike Day 3** — and deliberately
so, not an oversight. Day 3's labs took recorded WAV files as STT input
because that's what a modular pipeline consumes. Every lab here that talks
to Gemini sends **text or a generated image** as input and gets **audio
bytes back** — the point of native audio (Topic 01) is that the model
itself is the boundary between text/intent and speech, so there's no
separate "transcribe this recording" step for these labs to exercise. If
you want to see real audio bytes, `AM_H1`/`PM_H1`/`PM_H3` all write
real synthesized audio into `session.receive()`'s `inline_data` when a
real `GEMINI_API_KEY` is set — they just don't require you to supply any
to get started.

## Running the labs

Each lab folder has a `starter.py` (TODOs to fill in) and a `solution.py`
(reference). Both read any data files from their own folder.

```bash
cd AM_H1_banking_native_audio
python starter.py       # participant version
python solution.py      # reference — runs end-to-end
```

**Setup, all labs:**
```bash
pip install -r ../../requirements.txt
```
At minimum, `ANTHROPIC_API_KEY` should already be set (every lab in this
repo assumes it — `AM_H1`, `PM_H1`, `PM_H2`, and `PM_H3` all make real
Claude calls regardless of Gemini key status). For the real Gemini Live
API path:
```bash
export GEMINI_API_KEY=...   # or GOOGLE_API_KEY — ai.google.dev, free tier is enough
```

## How each lab ties back to the day's topics

- **AM_H1 Banking** → Topic 01 (pipeline to native audio) + Topic 06 (Gemini vs. the modular stack)
- **AM_H2 Insurance** → Topic 02 (affective dialogue & proactive audio)
- **AM_H3 Telecom** → Topic 03 (real-time multimodality) + Topic 04 (tool use & grounding)
- **PM_H1 Retail** → Topic 05 (production architecture), fusing AM_H1-H3
- **PM_H2 Banking** → Topic 07 (tooling & actions), Topic 06 made concrete via a swappable LangGraph node
- **PM_H3 Insurance** → Topic 08 (latency & reliability) + Topic 09 (compliance), the day's capstone fusion

See `Day6_Notes.md` for the full facilitator test-matrix / edge-case
companion, in the same format as `Day3_Notes.md`.
