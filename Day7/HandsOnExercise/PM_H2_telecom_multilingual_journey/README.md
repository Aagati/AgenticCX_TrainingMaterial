# PM · H2 — Telecom: Multilingual Journeys, Personas & Hand-off

**Track:** Telecom | **Industry angle:** a router-outage journey that starts in chat and continues on a voice call the next day

## Mental model: journey vs. session

A SESSION is one conversation, start to end. A JOURNEY is everything a
customer does across ALL sessions and ALL channels to resolve one problem.
Most "AI agent" demos only ever build sessions — this lab is about the
seam between them.

```
Touch 1 (chat, today)         Touch 2 (voice, tomorrow)
   utterance                     utterance
      │                             │
      ▼                             ▼
 LanguageRouter(locale)        LanguageRouter(locale)
      │                             │
      ▼                             ▼
 advance_turn()  ── writes ──►  JourneyMemoryStore  ──► reads ── advance_turn()
      │                     (keyed on customer_id,        │
      ▼                      NOT on channel/session)       ▼
   reply, stage                                        reply, stage
                                                            │
                                                    stage == "escalate"?
                                                            │
                                                            ▼
                                                    HandoffPackager
                                                  (always English output)
```

**Note on scope**: `channel` here is a plain string tag ("chat" vs.
"voice"), not a real audio pipeline — Deepgram/STT belongs to Day 3's
voice stack and Day 6's native-audio labs. The only thing this lab cares
about is that memory survives the channel switch, not how the audio got
transcribed.

## Localisation ≠ translation

Three things vary by locale, not just the language:

| Dimension | Example |
|---|---|
| **Language** | which language the reply is written in |
| **Persona / register** | `ja-JP` → highly formal, no contractions; `en-US` → casual, first-name basis — same agent, different social contract |
| **Legal disclosure** | wording that must appear verbatim, sourced from policy, never generated fresh by the model (a model paraphrasing a legal disclosure is a compliance bug, not a stylistic choice) |

All three come from ONE lookup (`locale_policies.json`), not three
separate systems — a new locale is a new JSON entry, not new code.

## The hand-off is a SEPARATE call, on purpose

It would be tempting to just forward the raw transcript to a human agent.
Don't — two reasons:
1. **Language mismatch.** The transcript may be in Japanese; the human
   agent picking up the case may not read Japanese. The hand-off bundle is
   always written in English, independent of what language the journey
   was conducted in.
2. **Compression.** A human taking over mid-journey needs the 3-sentence
   version and the durable facts, not a full replay — that's a
   summarization task, and summarization deserves its own call with its
   own prompt, not a repurposed reply.

## Memory: what belongs in it (and what doesn't)

| Belongs in `JourneyMemoryStore` | Doesn't belong |
|---|---|
| "Recurring evening outage, 4 nights running" | The full verbatim transcript |
| "Already tried: power-cycle x2, cable swap" | Small talk / pleasantries |
| "Customer explicitly asked for a technician, not more troubleshooting" | Anything already resolved and closed out |

Rule of thumb: a fact belongs in memory if a DIFFERENT agent, on a
DIFFERENT channel, would give a measurably worse reply without knowing it.

## When to reach for this pattern

- Your customers plausibly contact you more than once about the same
  issue, across more than one channel.
- You operate in more than one language/region and the difference is more
  than a dictionary swap (tone, formality, legal wording all shift too).
- Escalation to a human is a real path in your system, and that human
  needs a running start, not a cold open.

## Files
- `locale_policies.json` — language, persona tone, legal disclosure,
  formatting hints per locale.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Stretch goal
Swap the `channel="voice"` string argument for a real transcript produced
by Day 3's Deepgram pipeline (or Day 6's native-audio path) — nothing in
`JourneyOrchestrator` or `JourneyMemoryStore` should need to change, which
is itself the point: the memory layer shouldn't care how a channel
produced its text.

## Discussion (bring back to the group)
- `JourneyMemoryStore` here is in-process and lost when the script exits.
  What would change (schema, TTL, PII handling) if this were a real
  datastore shared across services and regions?
- The hand-off bundle is always English. What's the failure mode if the
  human agent pool is ALSO multilingual and some agents would rather read
  the original language?
