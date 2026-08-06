# Lab-3: Retail - The Transcript Log Is Leaking Card Numbers

**Track:** Retail | **Industry angle:** twelve support transcripts, half of
them carrying something that should never survive to disk, and a log file
that has been quietly keeping everything

**Facilitator note — this lab is self-paced and safe to skip.** Most of this
day's mechanics — layered checks, persistent logs, policy-as-config — were
already covered in Lab-1/Lab-2. This lab is deliberately small: one new,
contained idea. The Capstone does not depend on it: it ships `redact_for_log`
and a secure trace writer already built, and — unlike a lab that merely
explains the idea inline — the Capstone actively **enforces** it, because a
redaction bug in an enterprise pipeline is a breach, not a stale citation.

## Mental model: two different jobs

```
raw transcript                                     drafted reply
      │                                                  │
      │                                                  ▼
      │                                      response_leak_check()
      │                                      "never SAY it" -> reports, doesn't rewrite
      ▼
   redact()  ──findings──►  write_trace()  ───────►  redacted_trace_log.json
      │                          │                   "never STORE it"
   never returns          the ONLY writer
   the matched text       that touches this file
```

Most teams build the right-hand path and forget the left. The right-hand
path protects one customer in one conversation. The left-hand path is what
determines whether a database dump is an incident or a catastrophe.

## Two cases that make this harder than a regex (verified in testing)

| Case | Transcript | What happens | What this lab does about it |
|---|---|---|---|
| Looks like a secret, isn't | `TR-R07` — `ORD-4532110288219901` | The card pattern would match INSIDE an order number if matched naively | A negative lookbehind for `ORD-`, combined with a leading `\b` so the engine can't dodge the lookbehind by starting the match one digit later. One character (`\b`) is the difference between "fixed" and "still leaks" — this is a real bug this lab's own fixture caught during testing, not a hypothetical |
| Is a secret, doesn't look like one | `TR-R05` — card split across two turns (`"...4532 1102"` / `"8821 9901..."`) | Neither turn alone has 13+ digits | **Nothing.** This is a real limit of per-message pattern matching, worth knowing rather than engineering around in a lightweight lab. Closing it means stateful, cross-turn scanning — real scope beyond what this lab needs to prove the mechanism |

## Files
- `redaction_patterns.json` - 5 patterns, in match order: `api_key` and
  `card_number` (`critical`), `govt_id` (`high`), `email` and `phone`
  (`medium`).
- `retail_customers.json` - 12 customers, each with their own email (needed
  by `response_leak_check` to know "not this customer's own").
- `support_transcripts.json` - 12 transcripts: 5 clean, 2 card-number
  positives (one plain, one space-separated), one SSN+phone, one split-card
  negative, one order-number false-positive test, one agent-leaked email,
  one agent-pasted API key.
- `redacted_trace_log.json` - created at runtime; gitignored, grows every
  run.
- `starter.py` / `solution.py`

## Severity isn't decoration

`api_key` and `card_number` are `critical` and would page someone. `email`
and `phone` are `medium` and would land in a weekly report. Five patterns
with severities is barely more code than a flat denylist, and a completely
different operational posture once someone has to triage the findings.

## Setup
```bash
pip install anthropic python-dotenv
export ANTHROPIC_API_KEY=sk-ant-...
python starter.py
```

## Discussion (bring back to the group)
- `TR-R05`'s split card gets through. What would it cost — in state, in
  latency, in false positives — to catch a secret split across two
  messages, and who signs off on that trade?
- `redact()` is a denylist: it catches what you thought of. What would an
  allowlist look like for a support transcript, and why does almost nobody
  ship one?
- The findings list records *that* a card was found and never *which*. Is
  there any operational question you genuinely cannot answer without the
  raw value?
- Who owns `redaction_patterns.json` — the security team, the support team,
  or whoever last had an incident? What happens the first time someone adds
  a pattern that matches an order number, the way the original `card_number`
  pattern did until testing caught it?
