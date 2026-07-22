# Day 2 — Conversation Design, Multi-Agent, Memory, Channels

AM labs each isolate one primitive in reduced form (no tool-use API, plain
Python/single calls). PM labs upgrade the same idea into a real tool-use agent
loop, tiered memory, or a formal adapter boundary. Same "isolate then compose"
rhythm repeats on Day 3 and Day 4.

Run from repo root: `.venv/Scripts/python.exe Day2_Labs/<lab>/solution.py`

---

## AM·H1 — Banking: Slot-Filling Dispute Flow
`Day2_Labs/AM_H1_banking_slotfilling/` · intent → slot-fill → disambiguate → repair → confirm

**Structure**
- `REQUIRED_SLOTS` ordered list + `SLOT_PROMPTS` dict drive strict one-at-a-time asking.
- `extract_slot_value()` — narrow Claude call per slot, forced to reply raw value or literal `"NONE"`.
- `validate_slot()` — pure Python, no LLM: digit-strip (account), `strptime` (date), float-cast (amount), len-check (reason). Model extracts, code validates.
- Inner `while not filled and attempts < 3` per slot = bounded error-repair retries. Give-up escalates to a human after 3 failed attempts on ONE slot.
- `find_matching_transactions()` — plain filter; >1 match triggers numbered-list disambiguation via blocking `input()`.
- Whole flow runs on blocking `input()` (CLI simulation), not a `messages` list — this lab is about flow control, not API message-history mechanics.

**Test matrix** (interactive — drive via stdin)

| # | Sequence | Expected behavior |
|---|---|---|
| 1 | account `4471`, date `2026-07-10`, amount `45.00`, reason `"never received the item"` | Two transactions match on that account+date → disambiguation list shown (amount + merchant) → pick one → summary + confirm prompt → "Dispute filed." |
| 2 | amount given as `"forty-five-ish"` | `validate_slot` fails float-cast → "I couldn't read that as an amount..." → re-asks SAME slot, other filled slots untouched |
| 3 | 3 consecutive invalid answers on one slot | "I'm having trouble getting that information — let me connect you with a specialist." → flow exits early |
| 4 | reason `"no"` (4 chars) | Fails `len(v) < 5` check → re-prompted for a fuller reason |

**Edge cases to cover**
- Customer changes an earlier answer mid-flow ("actually, make that the 9th not the 10th") — README stretch goal, NOT implemented in the reference solution; current flow has no way to revisit a filled slot.
- Account+date combo with exactly ONE match vs ZERO matches — zero-match path falls back to `{"merchant": "(not found in our records)", ...}` rather than blocking — verify that's the behavior you want pedagogically (silent fallback vs hard stop).
- Compound answer in one message ("4471, July 10th, $45, never got the item") — `extract_slot_value` only asks for the CURRENT slot; does it correctly ignore the extra info, or does the model try to extract everything at once? This is the README's own discussion prompt.
- Disambiguation choice input that's out of range or non-numeric — falls to "I didn't catch a valid choice — let me connect you with a specialist," verify it doesn't crash.

---

## AM·H2 — Insurance: Supervisor Routes to Claims vs. Policy
`Day2_Labs/AM_H2_insurance_supervisor/` · classify → route → specialist persona (no tools yet)

**Structure**
- `classify_intent()` — 10-max-token call, forced single-word reply (`"claims"`/`"policy"`).
- `claims_specialist_reply()` / `policy_specialist_reply()` — each builds its own system prompt + scoped data, independent calls, no shared state.
- `route_and_respond()` — plain `if/else` on the classifier's output; routing is a code branch, NOT a tool call (PM·H1 rebuilds this as real tool-based handoff).

**Test matrix**

| # | Input | Expected routing | Expected content |
|---|---|---|---|
| 1 | "What's the status of my auto claim, CLM-3391?" | Claims Specialist | References CLM-3391 status/next step |
| 2 | "Does my auto policy cover a tow if my car breaks down?" | Policy Specialist | Cites `[POL-010]` (roadside assistance) |
| 3 | "My basement flooded from a burst pipe, am I covered?" | Policy Specialist | Cites `[POL-011]` (sudden plumbing failure covered) |

**Edge cases to cover**
- Ambiguous message that's genuinely both ("my claim CLM-3391 — does my policy even cover this kind of damage?") — classifier is forced to pick exactly one word, so it WILL commit to one specialist; is the wrong-specialist refusal ("that's outside what I handle") graceful?
- Add the README's stretch-goal 3rd category `"other"` for anything unclear, routed to a generic clarifying-question specialist instead of a forced guess.
- Skip the supervisor entirely and give ONE agent both specialists' instructions in one prompt (README's own comparison exercise) — measure response quality/latency difference directly, don't just assert it.
- Log every routing decision (message, chosen specialist) across a batch of test messages — seed of a routing-accuracy eval, foreshadows Day 5.

---

## AM·H3 — Telecom: Cross-Session Memory
`Day2_Labs/AM_H3_telecom_memory/` · persist durable facts → recall without re-asking

**Structure**
- `_load_store()`/`_write_store()` — whole-file JSON read/write, no locking (fine single-process, would race in prod).
- `save_fact()` — load whole store → `setdefault(customer_id, {})[key]=value` → write back.
- `extract_facts()` — narrow call forced to emit raw JSON (explicitly told no markdown fences), wrapped in `try/except JSONDecodeError` → `{}` fallback. Model output treated as untrusted.
- `chat()` — load profile → inject as bullets into system prompt if non-empty → reply → extract new facts from the message → persist.

**Test matrix**

| # | Session | Input | Expected |
|---|---|---|---|
| 1 | 1 | "Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan." | Reply addresses the slowness; `memory_store.json` now has `device_model: iPhone 15`, `plan_name: Unlimited Plus` (durable facts only — NOT "data is slow today") |
| 2 | 2 (fresh `chat()` call, store persisted from session 1) | "Hey, I have a question about my bill." | System prompt for this call already contains device+plan facts; agent doesn't ask for them again |

**Edge cases to cover**
- A message with ONLY session-specific info and no durable facts ("my data is slow right now") — `extract_facts` should return `{}`, confirm nothing spurious gets written.
- Model returns malformed JSON from `extract_facts` (happens occasionally with free-form extraction) — confirm the `try/except` fallback doesn't crash `chat()`.
- Saving something that's arguably NOT durable (customer's mood, a one-time complaint) — README's own discussion question: where's the line, and does your prompt's "DURABLE" instruction actually hold under a message like "I'm always frustrated with this network"?
- Two different `customer_id`s in the same run — confirm `save_fact`/`load_profile` never cross-contaminate.

---

## PM·H1 — Insurance: Supervisor + 2 Specialist Agents
`Day2_Labs/PM_H1_insurance_multiagent/` · real tool-calling handoff, 2-level agent hierarchy

**Structure**
- `run_claims_specialist()` / `run_policy_specialist()` — each a self-contained one-tool agent loop (call → `next()` tool_use check → execute → one followup → return text). Same shape as Day1 H2/H3's `run_turn`.
- `search_policy()` reuses Day1's tokenize/score/top_k retrieval verbatim, now living inside a tool function instead of a bare Python function.
- `HANDOFF_TOOL` — `specialist` constrained via JSON schema `"enum": ["claims","policy"]`, a schema-level guardrail AM·H2 didn't have.
- `execute_handoff()` — dispatch fn that calls the specialist's ENTIRE agent loop synchronously; its plaintext answer becomes the `tool_result` fed back to the supervisor. Supervisor's own followup call is what lets it relay "in its own voice" rather than parrot the specialist.
- System prompt explicitly tells the supervisor to skip handoff for greetings/thanks — the "no specialist needed" escape hatch.

**Test matrix**

| # | Input | Expected |
|---|---|---|
| 1 | "Hi there!" | Supervisor answers directly — NO handoff call |
| 2 | "What's the status of claim CLM-3391?" | Handoff to claims → `get_claim_status("CLM-3391")` → "under review, adjuster inspection" relayed |
| 3 | "Does my auto policy cover a rental car while my car's in the shop?" | Handoff to policy → `search_policy` → cites `[POL-012]` (rental reimbursement) |

**Edge cases to cover**
- Add a 3rd specialist (README stretch goal, e.g. Billing) — confirm `execute_handoff`'s dispatch and the `HANDOFF_TOOL` enum both extend without touching the handoff execution logic itself.
- A clarifying follow-up mid-specialist-conversation ("which claim did you mean?") — does the customer's next message correctly route back to the SAME specialist, or does the supervisor re-classify from scratch each turn? (Not handled in the reference solution — each `run_supervisor` call is stateless across turns.)
- What does the supervisor do with something that's neither claims nor policy nor a greeting (e.g. a billing question)? It will still force a claims/policy choice via the enum — is the forced misroute graceful?
- Nested-loop failure mode: what happens if the specialist's own tool call errors — does the error propagate cleanly up through `execute_handoff` to the supervisor's followup, or crash?

---

## PM·H2 — Banking: Episodic + Semantic Memory Across Sessions
`Day2_Labs/PM_H2_banking_memory/` · two-tier memory: durable facts vs. session history

**Structure**
- Store shape: `{customer_id: {"semantic": {...}, "episodic": [...]}}`. `_get_customer()` does `setdefault` to guarantee both keys exist.
- `add_episode()` — appends `{date, summary}`, unbounded growth (stretch goal: cap/summarize old entries, not implemented).
- `summarize_episode()` — NEW extraction type: post-hoc one-sentence summary of the WHOLE exchange, separate from `extract_semantic_facts()` (durable KV facts). Two different narrow calls doing two different jobs.
- `chat()` — builds system prompt from up to 2 optional blocks (`parts` list) — semantic bullets, episodic bullets — cleaner than AM·H3's single if/else.

**Test matrix**

| # | Session | Input | Expected |
|---|---|---|---|
| 1 | 1 | "Hi, I'm Priya. I'd like to dispute a $45 charge from Green Leaf Grocers on July 10th." | `semantic.preferred_name = "Priya"` saved; episodic entry logged for the dispute |
| 2 | 2 | "Any update on that dispute I filed?" | Reply references the Green Leaf Grocers dispute from episodic memory WITHOUT the customer restating merchant/amount |
| 3 | 3 | "Also, what's my account balance?" | Both semantic + episodic still present; episodic list now has 3 entries total |

**Edge cases to cover**
- Same merchant disputed twice in a month (README's own discussion question) — does the agent notice the *pattern*, or does it live as two disconnected episodic lines a human would have to spot manually? Test this directly with a 4th synthetic session.
- Episodic list growing past what's reasonable to inject into every system prompt — `load_recent_episodes(n=3)` caps it, but confirm the cap is actually being respected as history grows past 3.
- A fact that's ambiguous between semantic and episodic (e.g. "I always use email, never call me") — confirm `extract_semantic_facts` correctly classifies "communication_pref" as semantic, not folded into an episode summary.

---

## PM·H3 — Telecom: Channel Adapters with Shared State
`Day2_Labs/PM_H3_telecom_channels/` · normalize channel formats into one internal schema

**Structure**
- `adapt_chat()`/`adapt_email()` — pure data-shaping, both return the same 3-key dict (`customer_id`, `channel`, `text`); email's subject+body collapsed into one `text` string.
- `handle_message()` — identical body to AM·H3's `chat()` but takes the normalized dict and **never reads `normalized_message["channel"]`** — deliberately unused, proving channel-agnosticism structurally, not just by convention.
- `format_for_chat()`/`format_for_email()` — channel concerns pushed to the output boundary, symmetric with the input adapters.

**Test matrix**

| # | Call | Input | Expected |
|---|---|---|---|
| 1 | `adapt_chat` → `handle_message` → `format_for_chat` | "Hi, I'm on the Unlimited Plus plan and my WiFi calling keeps dropping." | Plain reply, no greeting/sign-off added; plan fact saved to memory |
| 2 | `adapt_email` → `handle_message` → `format_for_email` (SAME `customer_id`) | subject "Billing question", body "can you confirm my current plan and last bill amount?" | Reply wrapped with `"Hi,\n\n...\n\nBest regards,\nSupport Team"`; `handle_message` never branched on channel, yet the plan fact saved from the CHAT message is available answering the EMAIL |

**Edge cases to cover**
- Add a 3rd adapter (`adapt_sms`, README stretch goal) with a length-aware `format_for_sms` that truncates — confirm the shared core still needs zero changes.
- A channel-specific quirk (e.g. email's formal tone) accidentally leaking INTO `handle_message` instead of staying in the formatter (README's own discussion prompt) — deliberately break this on purpose once, to show trainees what the failure looks like and why it matters for adding a 4th/5th channel later.
- Same `customer_id` messaging on 2 channels in near-simultaneous succession — confirm the read-modify-write memory store doesn't lose an update (no locking, same caveat as AM·H3).
