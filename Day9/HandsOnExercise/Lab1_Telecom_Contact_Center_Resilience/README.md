# Lab-1: Telecom - The Call Center Falls Over the Moment It Gets Popular

**Track:** Telecom | **Industry angle:** eighteen contacts, one shift, and a downstream
system that stops answering right when the queues start filling up

## Mental model: two failure modes, neither fixed by a better prompt

```
contact_events.json (18 contacts, one simulated shift, t=0..260s)
        │
        ├──► classify_contact() ──────────► urgency/needs_human/summary
        │    (ONE model call, informational   (reported, never gates a branch -
        │     only - degrades, never raises)   the branch below is pure policy)
        │
        ├──► QueueRouter.select_queue() ──► which queue, how many hops shed
        │    + CapacityGovernor.admit()      (deterministic - skill + capacity)
        │
        └──► guarded_downstream_call() ───► clear | failed | short_circuited
             (CircuitBreaker OUTSIDE,         (deterministic - fixed fault
              ResilientCaller INSIDE)          schedule per contact_id)
                        │
        ┌───────────────┴───────────────┐
        ▼                                ▼
  downstream failed/short-circuited   downstream clear AND matched its
  OR shed all the way to overflow     own skill queue directly
        │                                │
        ▼                                ▼
  WarmHandoffPackager.build()      draft_holding_message()
  (model writes prose,             (cost-tiered: template/haiku/sonnet)
   system attaches facts)
```

Nothing about whether a contact gets a human or a cost-tiered draft depends
on what the model thought of it. `classify_contact`'s judgment is reported in
every record and never once decides a branch — the branch is decided by two
facts a monitoring dashboard would already have: is the downstream healthy,
and did this contact's own skill queue have room. That split is the lab:
model output informs, system state decides.

## Why the breaker sits OUTSIDE the retry, not inside

```
guarded_downstream_call
  breaker.allow_request(now)?
     NO  -> return short_circuited, ZERO physical calls
     YES -> ResilientCaller.call_with_retry(api.check)   <- up to 3 attempts,
              succeeds -> breaker.record_success            backoff+jitter
              fails x3 -> breaker.record_failure
```

Put retry on the outside and a single already-open breaker gets probed three
times per contact instead of zero — you've turned a circuit breaker into a
very elaborate way of tripling your load on a dependency that just told you
it's struggling. Breaker outside means the breaker gets the FIRST vote:
should we even try. Retry only ever runs once that vote is yes.

## Reading the shift (verified in testing — real API run)

| Fact | Value | Deterministic? |
|---|---|---|
| Breaker transitions | `closed→open@t=75`, `open→half_open@t=170`, `half_open→closed@t=170` | Yes — fixed fault schedule per contact_id |
| Final breaker state | `closed`, `consecutive_failures=0` | Yes — two clean downstream checks (CT-017, CT-018) reset the streak after CT-013/CT-016 each ticked it back up |
| Total physical attempts against `CoreStatusAPI` | 25 (across 18 contacts) | Yes |
| Contacts short-circuited (zero physical attempts) | 5 (`CT-007`–`CT-011`) | Yes — all arrive inside the open window |
| Contacts that shed at least one hop | 4 (`CT-006`, `CT-013`, `CT-014`, `CT-016`) | Yes |
| Handoff / self-serve split | 11 handoff / 7 self-serve | Yes |
| Self-serve tier mix | 5 haiku, 2 sonnet, 0 template (live) | Yes — the two premium contacts (`CUST-TC12`, `CUST-TC05`) are exactly the two that land self-serve with a clean downstream |
| Unassigned handoffs (no available agent with required skill) | 4 (`CT-006`, `CT-010`, `CT-014`, `CT-016`) | Yes — `HA-104` is the only escalation-skilled agent and is offline |
| `classify_contact`'s urgency/needs_human/summary | varies | **No** — real haiku judgment, reported only |

Run it twice: every row above except the last is byte-identical, because
none of them read the model's output. This wasn't tuned after the fact —
it's true because the branch that produces these numbers never touches
`classification`.

## Three things worth predicting before you read the code

- `CT-011` (technical, arrives right as the breaker opens) is short-circuited
  on the downstream call **and** still gets admitted into `Q-TECH-1`
  directly. Two independent systems, two independent verdicts on the same
  contact — a full downstream doesn't mean a full queue.
- `Q-TECH-1` and `Q-TECH-2` fill up in the middle of the shift (`CT-013`,
  `CT-014`, `CT-016` all shed), then `CT-017` and `CT-018` — arriving later —
  get admitted into `Q-TECH-1` **directly**, hops=0. Capacity isn't a ratchet;
  slots free up as `handle_seconds` elapses, so the SAME queue that was full
  ten minutes ago can take the next contact with zero shedding.
- `CT-010`'s `channel_intent` is `"other"` — it never had a primary queue to
  shed FROM, so it routes straight to `Q-OVERFLOW` at hops=0. That's a
  different `reason` (`no_matching_queue`) than `CT-006`'s hops=1
  (`capacity_shed`) even though both end up in the same queue — same
  destination, two different reasons a monitoring dashboard should not
  collapse into one number.

## New SDK surface: what the client gives you for free, and what it doesn't

- `Anthropic(max_retries=1, timeout=30.0)` — this lab turns the SDK's own
  hidden retry loop **down**, not up. The default client already retries
  transient failures for you; setting it to 1 (rather than accepting the
  default) is what makes `ResilientCaller`'s own attempts the ones a student
  actually observes in the printed trace, instead of two retry loops silently
  stacking on top of each other.
- `APIStatusError` / `APITimeoutError` / `RateLimitError` — the three
  exception types `classify_contact` catches by name. This is the first lab
  in the curriculum where a failure becomes a typed branch in the code
  instead of an uncaught traceback.
- **What the SDK does NOT give you**: a circuit breaker. `max_retries` makes
  one call more persistent; it has no concept of "stop trying this dependency
  altogether for the next 90 seconds." That's an application-level state
  machine, and it's the one primitive in this lab you have to hand-roll.

## When to reach for this pattern

- Your agent calls ANY downstream system that isn't the model itself — a
  CRM, a status API, a ticketing system — and that system can be slow or down
  without the model call failing at all.
- You're routing contacts into queues with real capacity limits, and "route
  by skill" alone doesn't answer "what happens when that skill's queue is
  full right now."
- You want a monitoring dashboard to be able to tell "the model thought this
  needed a human" apart from "the system's own state required a human" — two
  very different signals that are easy to accidentally merge into one flag.

## Files
- `ccaas_queues.json` — 5 queues (`Q-BILLING`, `Q-TECH-1`, `Q-TECH-2`,
  `Q-RETENTION`, `Q-OVERFLOW`) with `max_concurrent`/`handle_seconds`, plus
  the routing chain per intent.
- `agent_roster.json` — 5 human agents; `HA-104` is offline and the only
  escalation-skilled one.
- `contact_events.json` — 18 contacts, 16 unique customers (`CUST-TC02` and
  `CUST-TC05` each contact twice), a fixed `downstream_fault` per contact.
- `resilience_runs.json` — created at runtime by `append_shift_run()`;
  gitignored, grows every run.
- `starter.py` / `solution.py`

## Setup
```bash
pip install anthropic pydantic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- `classify_contact`'s `needs_human` is computed for every contact and never
  used to route one. Is that the right call for a telecom contact center, or
  is there a tier of "the model is very confident a human is needed" that
  should be allowed to override system policy?
- The breaker's `consecutive_failures` resets to 0 on ANY success, even one
  unrelated to the failures that almost tripped it open again (`CT-016` at
  consecutive=2, then two clean calls wipe it to 0). Is a pure consecutive-
  failure counter the right signal, or would a rolling error-rate over a
  time window catch something this design can't?
- `CT-017` and `CT-018` are both repeat contacts (`CUST-TC05`, `CUST-TC02`)
  and both land back in `Q-TECH-1` directly once capacity freed up. What
  would change about this design if you wanted a REPEAT contact to skip the
  queue entirely rather than compete for the same slots as a first-time one?
- Every handoff's `facts` dict is assembled by the system, never the model.
  What's the argument for letting the model draft even that structured part,
  and what specifically breaks if it hallucinates one field?
