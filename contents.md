# Agentic CX Specialisation — Day-by-Day Topic Index
### Week 1 of 2 · DE & AI Solutions

Build thread: one omnichannel CX agent, extended each day. Each day = Pre-lunch Concepts (4h) + Post-lunch Applied Lab (4h).

---

## Track tech stack (2026)
What learners build with, across the full week.
 
| Layer | What we use |
|---|---|
| Agent build | Claude Agent SDK, LangGraph, CrewAI; MCP + A2A (reference platforms: Sierra, Decagon, Intercom Fin, Agentforce, Lorikeet) |
| Models (the brain) | Claude Opus 4.8 / Sonnet 4.6, GPT-5.x mini, Gemini 3.x Flash |
| Voice — STT | Deepgram Nova-3 + Flux, AssemblyAI Universal-3, ElevenLabs Scribe v2; Krisp voice isolation |
| Voice — TTS | Cartesia Sonic-3, ElevenLabs Flash v2.5, Deepgram Aura-2 |
| Voice — orchestration | LiveKit Agents, Pipecat; managed Vapi / Retell; OpenAI Realtime, Gemini Live, ElevenLabs CAI 2.0 |
| Channels & systems | Chat, email, voice, SMS, WhatsApp; CRM / helpdesk (Salesforce, Zendesk, ServiceNow) via MCP |
| Eval & observability | LangSmith, Langfuse; voice QA (Hamming, Coval, Cekura); LLM-as-judge |
| Governance | ISO/IEC 42001, EU AI Act (voice disclosure), GDPR, DPDP; replayable audit trails |

---

## Day 1 — Agentic CX Foundations & a Resolution Agent
**Ships:** a working chat resolution agent that resolves a real customer query end-to-end (or escalates cleanly)

### Pre-lunch — Concepts
1. The CX agent landscape (2026)
2. Deflection vs. resolution
3. The agentic CX loop
4. Knowledge & grounding
5. Human-in-the-loop & escalation
6. Trust & guardrails (intro)

*Hands-on:* H1 Insurance (KB citation agent) · H2 Banking (action tool + confirmation) · H3 Retail (escalation handoff)

### Post-lunch — Applied Lab
1. Agent architecture
2. Resolution flows
3. Actions & confirmations
4. Persona & tone
5. Containment & escalation
6. Instrumentation

*Labs:* H1 Insurance → resolution agent (KB + action + escalation) · H2 Banking → safe-action agent (idempotent actions + approval gate) · H3 Retail → measured agent (instrumentation)

---

## Day 2 — Conversation Design, Multi-Agent CX & Omnichannel
**Ships:** a multi-agent CX system with persistent memory across at least two channels

### Pre-lunch — Concepts
1. Conversation design
2. Persona & policy
3. Multi-agent CX
4. Agent assist
5. Persistent memory
6. Omnichannel

*Hands-on:* H1 Banking (slot-filling dispute flow) · H2 Insurance (supervisor routing claims vs. policy) · H3 Telecom (cross-session memory)

### Post-lunch — Applied Lab
1. Supervisor orchestration
2. Specialist agents
3. Agent-assist mode
4. Memory architecture
5. Channel adapters
6. QA hooks

*Labs:* H1 Insurance → routed multi-agent CX flow (supervisor + 2 specialists) · H2 Banking → memory-enabled CX agent (episodic + semantic memory) · H3 Retail → agent-assist surface

---

## Day 3 — Voice Agents · the Real-Time Stack
**Ships:** a working voice agent that handles a real call end-to-end within the latency budget

### Pre-lunch — Concepts
1. The voice pipeline
2. STT / ASR
3. TTS
4. Orchestration
5. Turn-taking & interruptions
6. Build vs. buy

*Hands-on:* H1 Banking (LiveKit/Pipecat voice loop, measure latency) · H2 Insurance (tune turn-taking/endpointing) · H3 Telecom (bridge to a phone number via SIP)

### Post-lunch — Applied Lab
1. Pipeline assembly
2. Latency engineering
3. Telephony
4. Reliability
5. Voice eval & QA
6. Compliance

*Labs:* H1 Insurance → working voice agent (claim-status call + tool lookup) · H2 Banking → resilient voice pipeline (STT primary + fallback) · H3 Telecom → compliant call flow (AI disclosure + consent + recording)

---

## Day 4 — Actions, Integration, Guardrails & Compliance
**Ships:** a CX agent that safely takes a real system action, with guardrails and an audit trail

### Pre-lunch — Concepts
1. Enterprise integration
2. Action design
3. Guardrails
4. Prompt-injection & untrusted content
5. Identity & permissions
6. Compliance

*Hands-on:* H1 Banking (MCP ticketing system, create/resolve a ticket) · H2 Insurance (guardrails + prompt-injection defence, then attack it) · H3 Retail (per-user permissions on an order change)

### Post-lunch — Applied Lab
1. MCP integration
2. Transactional actions
3. Defence-in-depth
4. Escalation & safe failure
5. Policy-as-config
6. Compliance pack

*Labs:* H1 Banking → safe, audited action (idempotent + audited via MCP) · H2 Insurance → auditable agent (defence-in-depth guardrail stack + replayable audit trail) · H3 Retail → compliance pack (consent/disclosure/retention)

---

## Day 5 — Evaluation, ROI, Governance & Capstone
**Ships:** an evaluated, observable, governed CX agent + a one-page capstone brief

### Pre-lunch — Concepts
1. CX evaluation
2. Continuous QA
3. Observability
4. ROI
5. Governance
6. From PoC to production

*Hands-on:* H1 Insurance (resolution + trajectory eval suite over goldens) · H2 Banking (online QA, sentiment + escalation analysis) · H3 Retail (CX ROI model)

### Post-lunch — Applied Lab
1. End-to-end hardening
2. Eval-gated rollout
3. Governance pack
4. ROI dashboard
5. Capstone framing
6. Specialisation & next steps

*Labs:* H1 Banking → release-ready governance pack (agent card + audit + disclosure) · H2 Insurance → eval gate (resolution + safety) · H3 Team exercise → one-page capstone brief (problem, channels, metrics, eval plan)

**Problem Statement 2:** `Capstone_Telecom_Omnichannel_Agent/` (repo root) — a third, cross-cutting capstone alongside the Day 4 and Day 5 ones above, synthesizing multi-agent teams (Day 2) with governed, idempotent MCP actions and layered injection defense (Day 4) under full Langfuse cost + quality observability (Day 5).

---

## Week 2 — Advanced & Capstone
 
**Note:** the Week 2 source (image, not the original PDF) lists only "Major topics" per day — no dedicated
tech-stack table like Week 1's page 2. Where a specific platform/tool is named directly inside a day's
topic list (Day 6 only), it's called out separately below; the rest of Week 2 doesn't name specific
vendors/tools in what was shared.
 
### Day 6 — Advanced Voice & Multimodal CX with Google Gemini
**Major topics:**
From pipeline to native audio · Affective dialogue & proactive audio · Real-time multimodality ·
Production architecture · Tool use & grounding · Gemini vs. the modular stack · Tooling & actions ·
Latency & reliability · Compliance
 
**Named platforms/tools (only day in Week 2 with explicit stack references):** Google Gemini ·
Gemini Enterprise Agent Platform · Customer Engagement Suite · CX Agent Studio

**Hands-on only (no separate Applied Lab for this day):**
*AM* H1 Banking (native audio vs. modular pipeline) · H2 Insurance (affective
dialogue + proactive audio) · H3 Telecom (real-time multimodality + tool use
& grounding)
*PM* H1 Retail (production architecture, fuses AM H1-H3) · H2 Banking
(tooling & actions — LangGraph node, Gemini vs. Claude) · H3 Insurance
(latency/reliability + compliance, the day's capstone fusion)
See `Day6/HandsOnExercise/README.md` and `Day6_Notes.md` for the full
breakdown. The Gemini Enterprise Agent Platform / Customer Engagement Suite
/ CX Agent Studio row above is managed/console-driven with no SDK surface
to build hands-on against — covered as discussion material inside AM_H1
rather than as its own lab, the same treatment Day 3 gave "build vs. buy."
 
### Day 7 — Proactive, Outbound & Multilingual CX Agents
**Major topics:**
Proactive & outbound agents · Multilingual & localisation · Journey orchestration · Personalisation ·
Consent, compliance & brand safety · Measuring proactive value · Outbound orchestration · Memory
across the journey · Localised personas · Safety rails · Hand-off · Analytics hooks

**Production-shaped only (no separate AM/hands-on tier this day — every
lab goes straight to the PM_H* applied-lab pattern):**
*PM* H1 Banking (outbound & proactive orchestration — eligibility gate,
cost/channel-tiered drafting, measuring proactive value) · H2 Telecom
(multilingual journeys — locale personas, cross-channel memory, hand-off)
· H3 Insurance (consent, compliance & brand safety — outbound consent
gate, brand-safety linter, self-paced assignment) · H4 Retail (capstone —
personalised outbound journey agent, fuses H1-H3 + personalisation)
See `Day7/HandsOnExercise/README.md` and `Day7_Notes.md` for the full
breakdown. Facilitator pacing: H1/H2 led live, H3 self-paced, H4 the
combine-all capstone.
 
### Day 8 — CX Analytics, Personalisation & Continuous Improvement
**Major topics:**
Conversation analytics & insights · Continuous QA · Personalisation engines · Knowledge management ·
The improvement loop · Metrics that matter · Analytics pipeline · QA automation · Trace mining →
goldens · Eval-gated updates · Personalisation in the loop · Dashboards

**Production-shaped only (no separate AM/hands-on tier this day — same
treatment Day 7 gave its labs), naming follows a Lab-N pattern instead of
PM_H*:** *Lab-1* Telecom (conversation analytics pipeline — Batches API
insight extraction, matplotlib dashboards) · *Lab-2* Banking
(personalisation engine fused with continuous QA — mining, goldens, an
eval-gate decorator, prompt caching; carries personalisation since it has
no natural home in Lab-1's analytics and Lab-3 is this day's at-risk
self-paced slot) · *Lab-3* Retail (knowledge management — relevance vs.
trust, deprecated-article substitution; self-paced, safe to skip) ·
*Capstone* Insurance (fuses every primitive into one LangGraph, ships its
own self-check so it doesn't need a facilitator to grade it). See
`Day8/HandsOnExercise/README.md` and `Day8_Notes.md` for the full
breakdown. Facilitator pacing: Lab-1/Lab-2 led live, Lab-3 self-paced and
skippable, Capstone the combine-all, self-graded capstone.

### Day 9 — Enterprise CX at Scale: CCaaS, Reliability, Advanced Guardrails & Safety
**Major topics:**
CCaaS integration · Reliability at scale · Advanced guardrails · Identity & permissions · Compliance
at scale · Cost & capacity · Routing & handoff · Resilience engineering · Guardrail stack · Audit &
governance · Capacity & cost · Security
 
### Day 10 — Capstone Build & Shark Tank Finale
**Major topics:**
Integration · Proof of outcomes · Demo engineering · ROI & business case · Governance & safety ·
Pitch craft · Pitch · Demo · Proof · Q&A · Scoring · Next steps