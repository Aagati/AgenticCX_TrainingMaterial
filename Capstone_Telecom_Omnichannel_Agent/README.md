# Problem Statement 2 - Northwind Telecom Omnichannel Agent Team

**Track:** Telecom | **Time box:** ~5h30 core (trim variant ~4h, see below) | **Bonus tiers:** unbounded / take-home
**Ships:** a governed multi-agent team, backed by a real MCP server with idempotent actions, defended against prompt injection, priced and traced through Langfuse
**Week-1 Capstone · synthesizes Days 1-5 · companion to `Day4/HandsOnExercise/Capstone_Banking_MCP_Agent` (Days 1+4) and `Day5/Capstone_Lab_CX_Agent/lab30` (Days 1+4+5)**

## Who this is for

Candidates who have completed all five days of `HandsOnExercise` labs and want
one capstone that genuinely crosses all five, rather than three or four.
`Capstone_Banking_MCP_Agent` combines MCP + idempotency + guardrails +
permissions; `lab30` (ClaimsBot) combines grounding + governed actions +
trajectory eval + Langfuse. Neither combines **multi-agent teams** (Day2)
with the **MCP/permissions/injection-defense** stack (Day4) under
**Langfuse observability** (Day5) - that's the gap this capstone fills.

## Scenario

Northwind Telecom is a mobile carrier. Customers reach **NorthwindDesk**, a
front-line concierge that hands off to one of three specialists - billing,
plans, or technical support - each backed by real MCP tools instead of
plain Python functions. A prompt-injection attempt that talks the wrong
specialist into executing the wrong action (a **confused-deputy attack
across the handoff chain itself**, not just against a single tool) is the
central new risk this capstone introduces that none of the existing
capstones cover.

## Setup

```bash
cd starter
pip install -r requirements.txt          # or: pip install -r ../requirements.txt from repo root
python mcp_server.py                     # sanity check: starts clean, Ctrl-C to stop
```

Uses the repo-root `.env` via `load_dotenv()` - `ANTHROPIC_API_KEY` for Parts
3-4, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (optional) for Part 6's
Langfuse traces. Parts 1, 2, 5, and 6's offline half need **no API key at
all** - see the per-Part table below.

| Part | Time | Needs `ANTHROPIC_API_KEY`? | TODOs |
|---|---|---|---|
| 0 - Setup & orientation | 15 m | no | - |
| 1 - Grounded knowledge over MCP | 45 m | no | `retrieve` |
| 2 - Permissions & entitlements | 45 m | no | `check_permission`, `redact_for_role` |
| 3 - Idempotent MCP actions | 60 m | no | `_idempotent`, `apply_billing_credit`, `change_plan` |
| 4 - The agent team | 75 m | partly | `secure_call_tool`, `run_specialist`, `execute_handoff`, `run_turn` |
| 5 - Injection defense | 45 m | no | `layer_detect_instruction_injection`, `sanitize_retrieved_docs`, `output_guardrail` |
| 6 - Observability & cost | 45 m | no (Langfuse optional) | `record_usage`, `cost_report`, `score_transcript`, `evaluate_all`, `cost_gate` |

**Trim variant (~4h, fits a standard post-lunch block):** drop
`redact_for_role`, `change_plan`, and `cost_gate`; pre-implement
`sanitize_retrieved_docs` yourself before starting. 14 TODOs instead of 18.

## Files

```
starter/                     <- you edit this (look for # TODO N)
  mcp_server.py               FastMCP stdio server: tools + idempotency
  permissions.py               two-dimensional entitlement gate
  guardrails.py                input/output defense-in-depth layers
  cost.py                      Langfuse cost tracking
  agent_team.py                supervisor + 3 specialists, MCP client
  evaluate.py                  7-dimension trajectory scorer
  knowledge_base.py, accounts.json, entitlements.json,
    malicious_kb_docs.json, sample_transcripts.py,
    sample_usage_events.json, test_cases.json      <- given data, don't edit
solution/                    <- facilitator reference, complete
bonus/                        <- ungraded, see bonus/README.md
```

`diff -r starter/ solution/` differs in exactly the 6 Python modules and
nothing in the 7 data files - handy to confirm you haven't accidentally
edited a given file.

---

## Part 1 - Grounded Knowledge over MCP

**Draws on:** Day1 H1's keyword-retrieval + forced-citation pattern.

Implement `retrieve(query, k=3)` in `mcp_server.py`: tokenize, set-intersect
against each `KB_DOCS` entry, sort descending, keep only `score > 0`. No
embeddings needed at this scale (same justification as Day1 H1). `search_kb`
(given) just calls this.

**Definition of done:** every row in `test_cases.json`'s `retrieval_cases`
ranks the expected `doc_id` first when you call `retrieve()` directly; the
one zero-overlap query (`"what's the best cryptocurrency..."`) returns `[]`.
The agent physically cannot answer a question the KB doesn't cover, because
retrieval returns nothing - not because the prompt asked it nicely.

```python
from mcp_server import retrieve
retrieve("is there a cap on goodwill credits and do i need a documented reason")
# -> [{"doc_id": "TEL-BILL-03", ...}, ...]  (ranks first)
```

## Part 2 - Permissions & Entitlements

**Draws on:** Day4 AM_H3's ownership-gate pattern, extended to two
dimensions.

Implement `check_permission()` in `permissions.py`: (A) does the customer
own the account (`accounts.json`), (B) does the **calling specialist's
role** have the tool in its `allowed_tools` and, if relevant, is the amount
within its `max_credit_cents` limit (`entitlements.json`). Order matters:
ownership is checked before role capability, so a request that fails both
always reports `not_owner` - same contract as AM_H3.

**Definition of done:** all 10 rows in `test_cases.json`'s `permission_cases`
match on both `allowed` and `reason`. The row where ownership *and* role
would both fail must return `not_owner`, never `tool_not_allowed_for_role` -
if your check order is backwards, that one row fails and nothing else does.

## Part 3 - Idempotent MCP Actions

**Draws on:** Day4 PM_H1's idempotency-key pattern, extended from one
branch to three.

Implement `_idempotent()`, `apply_billing_credit()`, and `change_plan()` in
`mcp_server.py`. Three branches, not two: key absent -> run + store; key
present + **matching** args -> return the stored result verbatim
(`_replay` audit entry, no mutation); key present + **different** args ->
`{"status": "conflict"}` (`_conflict` audit entry, no mutation). State
lives in `PROCESSED_KEYS`, server-side only - a network retry re-invokes
the external system, not whichever agent process happened to be running
(Day4's own documented anti-pattern warning).

**Definition of done:** call `apply_billing_credit` twice with the same key
and same args -> identical result, `AUDIT_LOG` gains one `_replay` entry,
balance moves once. Same key with a *different* amount -> `"conflict"`,
balance unchanged. Kill and restart your Python process, re-fire the same
key against the still-running server (or re-import in a fresh script) -
the replay still works, because the state was never in your process.

## Part 4 - The Agent Team

**Draws on:** Day2 PM_H1's supervisor+specialist handoff pattern, extended
to 3 specialists whose tools are real MCP tools instead of plain functions.

Implement `secure_call_tool()`, `run_specialist()`, `execute_handoff()`,
and `run_turn()` in `agent_team.py`. `secure_call_tool()` is the load-
bearing one: it rejects any tool name not on the calling role's allowlist
**before any network call** (kills a rogue lookalike tool name and a
confused-deputy handoff with zero MCP round-trips), and overwrites
whatever `customer_id`/`agent_role` the model supplied with the real
authenticated context (Day4 capstone's identity-override pattern, extended
to the role dimension).

**Definition of done:** run `python agent_team.py` (needs
`ANTHROPIC_API_KEY`) - all 6 scripted scenarios complete without a crash,
the full audit trail at the end shows a ticket creation, a permission
denial, and a credit apply/replay/conflict sequence. Separately,
`secure_call_tool` rejecting an unlisted tool name is checkable with **zero
API key**: call it directly with a tool name not in a role's
`allowed_tools` and confirm `session.call_tool` is never reached.

```
=== Scenario 5: entitlement gate - two different customers, identical request ===
cust_1001: [substantive reply, credit discussed]
cust_2002: [generic decline - no data leaked; audit trail shows get_account_denied/not_owner]
```

## Part 5 - Injection Defense

**Draws on:** Day4 AM_H2/PM_H2's layered input/output guardrail
architecture, extended to scan every retrieved doc (not just the top
result) and to check the reply against the session's own context.

Implement `layer_detect_instruction_injection()`, `sanitize_retrieved_docs()`,
and `output_guardrail()` in `guardrails.py`. `sanitize_retrieved_docs()`
runs **every** doc `search_kb` returns through the input layers - a
multi-hop attack (see the bonus tier's RT-04) plants its payload in a
low-ranked doc specifically because a defense that only scans `doc[0]`
will never see it. `output_guardrail()` checks the final reply for a
citation that was never actually retrieved, an account number this
customer doesn't own, or a leaked idempotency key.

**Definition of done:** all 5 ids in `malicious_kb_docs.json` land in
`sanitize_retrieved_docs()`'s blocked list; **all 12 clean `KB_DOCS` pass
through unmodified** - zero false positives is half the grade, since a
filter that blocks everything is not a defense, it's an outage.

## Part 6 - Observability & Cost

**Draws on:** Day5's Langfuse tracing pattern (lab30's `traced()` no-op-if-
unconfigured convention) - extended with something no lab in this course has
done yet: **every existing Langfuse use logs quality scores, never actual
token cost.**

Implement `record_usage()` and `cost_report()` in `cost.py`, and
`score_transcript()`, `evaluate_all()`, and `cost_gate()` in `evaluate.py`.
`record_usage()` computes a dollar cost per model call from
`response.usage` and appends it to a ledger; `cost_report()` aggregates it
**by agent role** - the multi-agent-specific payoff: you'll see the
supervisor's relay turn costs real money too, and that an inefficient
handoff roughly doubles the bill. `score_transcript()` extends Day5
lab30's 4-dimension eval to 7: grounding, **routing** (right specialist?),
**authorization** (right *executing role*, not just the replying
persona?), **idempotency** (did a retry reuse the original key?),
confirmation, efficiency, and **cost** (within budget?).

**Definition of done:**
```python
from cost import cost_report, load_sample_usage
report = cost_report(load_sample_usage())
# total_cost_usd == 0.04245 (to within $0.0001), by_agent_role has exactly 4 keys, conversations == 3

from evaluate import evaluate_all
result = evaluate_all()
# exactly 3 of 8 transcripts pass (T1_clean_credit, T6_correct_escalation, T8_clean_plan_change);
# each of the other 5 fails exactly ONE dimension, named in its notes.
```

With Langfuse keys set: one trace per conversation, `cost_usd` and all
seven dimension scores visible as numeric scores in the UI, grouped by
`session_id` in the Sessions view.

**A note on live-run cost vs. the graded fixture:** `sample_usage_events.json`
is deliberately kept under `PER_CONVERSATION_BUDGET_USD` so Part 6's
grading is unambiguous. A real live conversation with several tool
round-trips (Part 4's scripted scenarios) often costs *more* than that -
expect `cost_report()` to occasionally report `budget_exceeded: true` when
run against your own `USAGE_LEDGER` after a live session. That's a
feature, not a bug: it's worth discussing with candidates why a tight
per-conversation budget looks fine on paper and gets exceeded in practice.

---

## Observability (given, not a TODO)

Every specialist call and the supervisor's own turn are traced via the
same `traced()` no-op-if-unconfigured decorator as Day5's lab30 - the
whole lab stays runnable with zero Langfuse keys. What's new versus every
other Langfuse use in this course: `cost.py`'s `record_usage()` logs an
actual `cost_usd` numeric score per call, and every span in one
conversation shares a Langfuse `session_id` so a handoff renders as one
grouped session in the UI (confirm the exact `update_current_trace()`
call against your installed `langfuse==4.14.1` before relying on it in a
real deployment - see `agent_team.py`'s `_set_trace_session()` docstring).

## Stretch goals (not implemented in the reference solution)

- `redact_for_role()` / a `supervisor_override` role that can act on any
  account regardless of ownership - the single juiciest prompt-injection
  target in the whole system if you build it; discuss what would need to
  change in `check_permission()`'s check order to add it safely.
- Langfuse **Datasets**-based regression experiments across multiple
  `agent_team.py` runs, instead of the single-run `cost_report()` here.
- A `max_amount` guardrail inside `apply_billing_credit` itself (Day4
  PM_H1's own stretch goal, direct extension of the ownership-gate pattern
  applied to a dollar amount instead).
- See `bonus/README.md` for the three larger bonus tiers: an MCP-aware red
  team, a real-Deepgram voice channel, and LangGraph/Claude-Agent-SDK
  alt-stack reimplementations.

## Wrap-Up - Reflection

1. `secure_call_tool()`'s role-allowlist check and `permissions.check_permission()`
   both gate `apply_billing_credit`. Are they redundant with each other?
   What does each one catch that the other doesn't?
2. `sample_transcripts.py`'s T4 has the **billing** specialist correctly
   voicing the reply while the underlying tool call carries `tech_agent`
   as the executing role. Why does that combination - right persona,
   wrong executing role - matter more in a multi-agent system than in a
   single-agent one?
3. If you only had budget to harden ONE of Part 5's three checks
   (`layer_detect_instruction_injection`, `sanitize_retrieved_docs`,
   `output_guardrail`) before a real launch, which would you pick, and
   what risk are you accepting by leaving the other two as given?
