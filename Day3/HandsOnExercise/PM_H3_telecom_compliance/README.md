# PM · H3 — Telecom: AI Disclosure + Consent + Recording Handling

**Track:** Telecom | **Time box:** ~30 min | **Ships:** a compliant call flow
**Pattern practiced:** mandatory disclosure gate, consent capture, and a data-erasure path — before any conversation logic runs

## Scenario
From 2 August 2026, the EU AI Act's Article 50 requires that AI systems
interacting with people disclose that fact. Combined with call-recording
consent laws (which vary by jurisdiction but are a near-universal
requirement) and GDPR's right to erasure, a compliant voice agent needs
three things to happen *before* — and sometimes *after* — the actual
conversation: a disclosure, a consent capture, and an erasure path.

## Your task
Wrap this afternoon's H1 voice agent pattern with a compliance layer:
1. `disclose_ai(call_log)` — the very first thing that happens after
   `answer`, before any customer speech is processed: state clearly that
   the caller is speaking with an AI assistant, and log that the
   disclosure was given (with a timestamp) to `call_log`.
2. `request_recording_consent(call_log)` — ask the caller for consent to
   record the call, and (for this simulated lab) treat any caller response
   that isn't an explicit refusal as consent — log the outcome. If the
   caller refuses, the call should continue WITHOUT recording (log that
   distinction) rather than blocking the call entirely.
3. `check_erasure_request(text)` — a narrow check (keyword or a lightweight
   Claude call, your choice) for whether the caller is asking to have
   their data deleted ("delete my data," "erase my recording," "forget
   this call"). If detected, the agent should confirm the request back to
   the caller and log an erasure request — not silently ignore it.
4. `compliant_call_flow(events)` — wraps AM·H3's state machine so that
   `disclose_ai` and `request_recording_consent` happen automatically right
   after `answer`, before any `speech` event reaches the LLM.

Run the provided `simulate_call()` (includes a caller asking to have their
data deleted partway through) and confirm the full `call_log` at the end
shows: disclosure given, consent outcome, every turn, and the erasure
request — a real audit trail.

## Why this matters
This is today's Topic 06 (compliance). The discipline here is the same
shape as Day 1's guardrails: these are requirements the call flow must
satisfy structurally — a disclosure that only happens if the model
"remembers" to say it isn't a disclosure a compliance team can rely on.
Building it as a mandatory gate in the state machine, with a logged audit
trail, is what makes it auditable rather than aspirational.

## Files
- `starter.py` — scaffold with TODOs, includes `simulate_call()`.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Make the disclosure language configurable per-locale (a US caller and an
  EU caller may need different disclosure wording/legal basis) and pick it
  based on a simulated `caller_region` field.
- Add a `call_log` export to JSON so the audit trail could actually be
  handed to a compliance reviewer, not just printed to console.

## Discussion (bring back to the group)
- If a caller asks for erasure mid-call, should the agent stop referencing
  anything from earlier in the SAME call for the rest of the conversation,
  or does erasure only apply going forward to storage? Where's the line
  between "delete my data" and "I want you to forget everything right now"?
