# PM · H3 — Telecom: Channel Adapters with Shared State

**Track:** Telecom | **Time box:** ~20 min | **Ships:** an omnichannel-ready agent
**Pattern practiced:** normalize multiple channel formats into one internal schema, share memory/state across them

## Scenario
The same customer messages you on live chat in the morning and sends an
email in the afternoon. Today's Topic 05 (channel adapters) is about making
those two very different message formats — a short chat bubble vs. a
subject+body email — look identical to the agent core underneath, so the
*same* agent logic and the *same* memory store handle both without special
casing.

## Your task
Build:
1. A common internal schema:
   ```python
   {"customer_id": "...", "channel": "chat" | "email", "text": "..."}
   ```
2. `adapt_chat(customer_id, message)` — trivial passthrough into the schema.
3. `adapt_email(customer_id, subject, body)` — combine subject + body into
   a single `text` field in the schema (e.g. `"Subject: ...\n\n..."`).
4. `handle_message(normalized_message)` — the ONE agent core function that
   takes a normalized message (regardless of original channel), loads that
   customer's memory (reuse this morning's `save_fact` / `load_profile`
   pattern, or PM · H2's semantic store if you finished that lab), gets a
   reply, and updates memory — with no channel-specific branching inside it.
5. A response formatter per channel: `format_for_chat(reply)` (passthrough)
   and `format_for_email(reply)` (wraps it with a greeting + sign-off
   appropriate for email).

Demonstrate: send one message in via `adapt_chat`, and a second in via
`adapt_email` for the **same customer_id**, and show that `handle_message`
didn't need to know or care which channel each one came from — while the
memory saved from the chat message is available when handling the email.

## Why this matters
This is the concrete version of "one engine across chat, email, voice, SMS
and WhatsApp with shared state" from this morning's Topic 06. The adapters
are intentionally the *only* channel-specific code — everything else
(reasoning, memory, tools) stays channel-agnostic, which is what makes
adding a sixth channel later cheap instead of a rewrite.

## Files
- `starter.py` — scaffold with TODOs. Reuses the memory pattern from AM · H3.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a third adapter, `adapt_sms(customer_id, text)`, with a length-aware
  formatter that truncates `format_for_sms` replies to a realistic SMS
  length instead of sending a wall of text.
- Track which channel each episode/memory update came from, so the agent
  could (in principle) say "you mentioned this over email last week."

## Discussion (bring back to the group)
- What breaks if a channel-specific quirk (e.g. email's formal tone) leaks
  into the shared `handle_message` core instead of staying in the
  formatter? Why does that matter for adding a 4th and 5th channel later?
