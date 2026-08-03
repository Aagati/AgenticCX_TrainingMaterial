# Day 7 — Proactive, Outbound & Multilingual CX Agents

Four labs, all production-shaped (`PM_H*`) — Day 7 skips the AM
warm-up tier Day 6 used and goes straight to the applied-lab pattern.
Realistic facilitator pacing: **PM_H1 and PM_H2 are facilitator-led**
(the two heaviest, richest labs), **PM_H3 is a self-paced assignment**
(deliberately kept to deterministic Python + two model calls, so it's
debuggable without a facilitator in the room), and **PM_H4 is the
capstone** — it fuses every primitive from H1-H3 into one **multi-agent
LangGraph** and adds the one genuinely new piece, personalisation.

Every lab in this repo assumes `ANTHROPIC_API_KEY` is configured — Day 7
is Claude-only, no other vendor keys, no real-if-key/simulated-fallback
branching (that pattern belongs to Day 3/Day 6's voice vendors, not here).
`PM_H4` additionally uses `langgraph` (a library, not a vendor key) to
express its orchestration as an actual multi-agent graph rather than
branching Python — same dependency Day 6's `PM_H2` used, no new
credential required.

Run from repo root: `.venv/Scripts/python.exe Day7/HandsOnExercise/<lab>/solution.py`

**A note on "proactive"**: Day 6 used this word for a Gemini Live session
volunteering unprompted audio mid-call. Day 7 uses it for something
upstream of any call: a campaign engine deciding to initiate contact at
all. Same word, two different layers of a CX system — see PM_H1's README
for the full note.

---

## Labs

| Folder | Lab | Industry | Facilitator pacing | Topics covered |
|---|---|---|---|---|
| `PM_H1_banking_outbound_proactive` | Outbound & Proactive Orchestration | Banking | **Led live** | Outbound orchestration, proactive agents, measuring proactive value, analytics hooks |
| `PM_H2_telecom_multilingual_journey` | Multilingual Journeys, Personas & Hand-off | Telecom | **Led live** | Multilingual & localisation, localised personas, memory across the journey, hand-off |
| `PM_H3_insurance_consent_safety` | Consent, Compliance & Brand Safety | Insurance | Self-paced assignment | Consent/compliance/brand safety, safety rails |
| `PM_H4_retail_capstone_journey` | Capstone — Personalised Outbound Journey Agent | Retail | Capstone (combine-all) | Personalisation + every H1-H3 topic, fused |

## What compounds into what

`PM_H4` doesn't import H1-H3's code — it re-implements a thin,
retail-flavored version of each primitive, the same "compound, don't
cross-import" move Day 6's `PM_H1` used for its AM labs, and wires them
into a LangGraph multi-agent graph rather than a flat function chain —
combining Day 2's supervisor+specialist pattern with Day 6 PM_H2's graph
pattern:

- `ConsentGate` / `EligibilityEngine` — H3/H1's gates, thinned, wrapped as
  deterministic graph NODES (no model call).
- A supervisor-style conditional router delegates to whichever
  SPECIALIST AGENT the situation calls for: `EscalationAgent` (H2's
  `HandoffPackager`), or `TieringAgent` (H1's cost-tiered
  classify→draft/template, crossed with H2's locale persona and the new
  segment→offer lookup).
- `ComplianceAgent` + `RepairAgent` (H3's linter + one-shot repair) form
  the graph's one LOOP — a specialist's output judged, revised by another
  specialist, and re-judged, the piece of agentic behavior a flat
  pipeline can't express as cleanly.
- **Personalisation** — new: a segment→offer lookup crossed with the
  locale→persona lookup, the piece none of H1-H3 needed on their own.

## Supplementary data files

Every lookup lives in its own JSON fixture in the lab folder, same
policy/knowledge-base-as-config convention Day 4/5/6 used:

| Lab | File | What it holds |
|---|---|---|
| `PM_H1` | `customer_profiles.json` | balance, consent, timezone, contact history per customer |
| `PM_H1` | `campaign_policies.json` | triggers, channel tiers/quiet hours, frequency cap, baseline conversion rates |
| `PM_H2` | `locale_policies.json` | language, persona tone, legal disclosure, formatting hints per locale |
| `PM_H3` | `consent_registry.json` | per-customer channel opt-in, do-not-contact, consent capture date |
| `PM_H3` | `brand_safety_policy.json` | banned phrases, required disclosures per message type, consent freshness window |
| `PM_H4` | `retail_offer_catalog.json` | segment→offer mapping, channel tiers, banned phrases, required disclosure |

`PM_H4`'s customer fixture is a small Python literal inside `solution.py`
itself, not a JSON file — deliberate, so the capstone doesn't depend on
reading another lab's data file to run standalone.

## Running the labs

Each lab folder has a `starter.py` (TODOs to fill in) and a `solution.py`
(reference, runs end-to-end). Both read any data files from their own
folder.

```bash
cd PM_H1_banking_outbound_proactive
python starter.py       # participant version
python solution.py      # reference — runs end-to-end
```

**Setup, all labs:**
```bash
pip install anthropic pydantic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
```

## How each lab ties back to the day's topics

- **PM_H1 Banking** → Outbound orchestration, proactive agents, measuring
  proactive value, analytics hooks
- **PM_H2 Telecom** → Multilingual & localisation, localised personas,
  journey orchestration, memory across the journey, hand-off
- **PM_H3 Insurance** → Consent, compliance & brand safety, safety rails
- **PM_H4 Retail** → Personalisation, fusing every topic above into one
  pipeline

See `Day7_Notes.md` for the full facilitator test-matrix/edge-case
companion, in the same format as `Day6_Notes.md`.
