# PM · H1 — Banking: Outbound & Proactive Orchestration

**Track:** Banking | **Industry angle:** payment-due and fraud campaigns fired by business events, not by a customer message

## Mental model: the outbound loop

An outbound campaign has no incoming turn to react to — the system has to
manufacture the trigger, the audience, and the judgment call about how much
to spend on each case, all before a customer says anything.

```
TRIGGER fires (due date, fraud signal, ...)
   │
   ▼
ELIGIBILITY  — deterministic, no model call
   consent?  quiet hours?  frequency cap?  does the trigger even apply?
   │  (fails any check → excluded, done)
   ▼
TIER  — cheap model decides
   "does this case need a bespoke message, or is a template enough?"
   │
   ├─ low  → template (0 tokens)
   └─ high → capable model drafts a bespoke message
   │
   ▼
SEND (channel-tiered: sms/email cheap+async, voice expensive+sync)
   │
   ▼
LOG  → analytics event (customer, channel, tier, model, cost, timestamp)
   │
   ▼
MEASURE  — did reaching out change the outcome vs. a control group?
```

**Note on the word "proactive"**: in Day 6's Gemini Live labs, "proactive"
meant the model volunteering an unprompted audio message mid-call. Here it
means something upstream of any call: a campaign engine deciding to
initiate contact at all. Same word, two different layers of a CX system —
don't conflate them.

## Eligibility checklist (apply ALL, in any order)

| Check | Question | Data source |
|---|---|---|
| Trigger match | Does this customer's state satisfy the trigger's condition? | `campaign_policies.json["triggers"][id]["match"]` |
| Consent | Has this customer opted in on their **preferred channel specifically**? | `customer["consent"][channel]` |
| Frequency cap | Has enough time passed since we last contacted them? | `last_contacted_days_ago >= frequency_cap_days` |
| Quiet hours | Is it currently within the do-not-disturb window **in the customer's own timezone**? | `channel_tiers[channel]["quiet_hours"]`, converted via `timezone_offset_hours` |

A customer can fail for more than one reason — in practice you only need
the first failing check to exclude them, but when debugging a "why wasn't
this customer contacted" question, check all four independently rather than
assuming the first hit is the only cause.

## Quiet-hours math (the part everyone gets wrong once)

A window like `[21, 8]` means "quiet from 9pm to 8am" — it **wraps
midnight**, so you can't just check `start <= hour < end`:

```
if start > end:      # wraps midnight, e.g. 21 -> 8
    quiet = hour >= start or hour < end
else:                 # doesn't wrap, e.g. 22 -> 6 is NOT this case
    quiet = start <= hour < end
```

And the hour you check is **local to the customer**, not your server's
clock: `local_hour = (dispatch_hour + customer_timezone_offset) % 24`.

## Tiering decision table

| | Cheap tier | Expensive tier |
|---|---|---|
| **Channel** | SMS / email — async, no live human on the other end | Voice — synchronous, ties up a line |
| **Model** | Haiku-class — classification, templated fill-in | Sonnet/Opus-class — bespoke drafting |
| **When to use it** | Default. Most campaign sends are routine reminders. | Only when a cheap classifier flags the case as needing judgment — fraud, edge-of-due-date-with-insufficient-balance, anything where a wrong or tone-deaf message costs more than the model call would've. |

The tiering decision itself should be made by the CHEAP model — deciding
"does this need a bespoke message" is itself a cheap classification task.
Only the drafting step, once triggered, should pay for the capable model.

## Measuring proactive value

The only way "proactive outreach works" becomes a defensible claim instead
of an assumption is a control group:

```
uplift_pp = (contacted_conversion_rate − control_conversion_rate) × 100
```

If you can't hold out a control group in production (e.g. legal/ethical
reasons to always contact fraud victims), the fallback is a **before/after**
comparison against a rolling historical baseline — weaker evidence, but
still better than "we sent messages and things seemed fine."

## When to reach for this pattern

- You have a **business event**, not a customer message, as the reason the
  conversation exists.
- You need to decide, at scale, **whether** to spend a model call on a
  message before you decide **what** the message says.
- Someone will eventually ask "did this campaign actually help?" — build
  the measurement hook before that question arrives, not after.

## Files
- `customer_profiles.json` — mock customer fixture (balance, consent,
  timezone, contact history).
- `campaign_policies.json` — triggers, channel tiers/quiet hours,
  frequency cap, baseline conversion rates.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- The cheap model decides urgency for every trigger type with the SAME
  classifier prompt. Would a fraud-specific classifier catch things a
  generic one misses — and is that worth maintaining two prompts?
- Quiet hours here are a single window per channel. Real regulations
  (TCPA-style) vary the window by day of week and jurisdiction — how much
  of that belongs in the policy JSON vs. in code?
