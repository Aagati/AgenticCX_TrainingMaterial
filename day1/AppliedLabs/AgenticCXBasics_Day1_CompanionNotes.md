# Day 1 — Post-Lunch Applied Lab: Companion Notes

**Notebook:** `AgenticCXBasics_Day1AL.ipynb` · **Lane:** Insurance · **Duration:** 4h

The notebook itself now carries the walkthrough — each code cell has an explanation directly above
it covering what it does and why it's built that way. This document doesn't repeat that. It goes
one layer deeper: the reasoning, misconceptions, and production context behind each lab, organized
the same way the notebook is, for use as background reading or reference when a question goes
beyond what's on the page.

---

## Setup

The Agent SDK's dependency on the Claude Code CLI surprises people coming from a pure-API
background — it's easy to assume the SDK is just a Python wrapper around HTTP calls to Anthropic.
It isn't: it shells out to the CLI as its execution runtime, which is why the CLI install is a hard
prerequisite rather than a nice-to-have.

The top-level-`await` requirement is a Jupyter/IPython detail, not an SDK one — the SDK's client
methods are `async` because tool calls and multi-turn conversations are inherently I/O-bound, and
Jupyter's autoawait support lets that run without wrapping every cell in `asyncio.run()`. Outside a
notebook, the same code needs an explicit `async def main(): ... ; asyncio.run(main())`.

---

## Architecture

This section is new as of this revision — the notebook previously went straight from Setup into
Step 1 with no explicit map of the pieces, which meant trainees met `ClaudeAgentOptions`,
`create_sdk_mcp_server`, and the CLI-as-runtime fact in three separate, unconnected moments instead
of as one coherent picture. The fix is a single markdown cell before Step 1 that names all five
pieces (`ClaudeSDKClient`, `ClaudeAgentOptions`, the CLI subprocess, the model, the in-process MCP
server) and how a message flows through them, with a doc link per piece.

**Why this belongs before Step 1, not folded into Step 2 where the first tool actually gets
built:** by the time trainees reach Step 2's tool-registration mechanics, they're already juggling
`mcp_servers` dict-vs-list and the `allowed_tools` naming convention — that's the wrong moment to
also be absorbing "what is a runtime, conceptually." Separating the map (architecture) from the
first use of a piece on it (Step 2) means a confused trainee in Step 2 can be pointed back at a
diagram they've already seen once, rather than encountering the whole concept for the first time
mid-debug.

**The tie-back to the pre-lunch "agentic CX loop" concept is deliberate, not decorative.** Trainees
who sat through the morning session heard perceive → reason → act → observe as an abstract loop;
this section is the first moment that loop gets a concrete Python object at each step
(`ClaudeSDKClient.query()` → the model's tool-use decision → the `@tool` function call → the
`tool_result` returned to the model). If a trainee can't point at which line of code corresponds to
which stage of the morning's loop, that's a sign the connection needs to be made explicit verbally,
not just left on the page.

**On the `ClaudeAgentOptions` fields listed as "exists, not used today"** (`permission_mode`,
`hooks`, `max_turns`, `model`, `cwd`/`setting_sources`): these are named specifically to pre-empt a
predictable class of question ("can it also approve tool calls interactively instead of a static
allowlist?" — yes, `permission_mode`, that's Day 4 territory) without going down that path today.
Naming a capability and deferring it is different from trainees not knowing it exists at all — the
former means "not yet," the latter means a trainee reinvents a worse version of it in their own
capstone because they didn't know the SDK already had it.

---

## Step 1 — The knowledge base

The keyword-overlap scorer is a stand-in, but it's worth being explicit about *what* it stands in
for, because the failure modes are different. A keyword scorer fails on synonyms and paraphrase —
ask about a "loaner car" instead of a "rental car" and it may miss POL-9.1 entirely, even though a
human reading the question would immediately connect the two. A real embedding-based retriever
fails differently: it's more robust to phrasing but can retrieve something *semantically close* yet
*substantively wrong* — which is arguably a harder failure to catch, because it looks like a
reasonable match. Retrieval quality problems don't disappear when embeddings replace keyword
matching; they change shape.

The POL-4.2 / POL-9.1 pairing is the pedagogical core of Lab 1. It's a realistic instance of a
general problem in policy documents: exclusions and their overriding riders are almost always
written in separate clauses, because that's how insurance products are actually built up (base
policy plus optional riders). Any retrieval system built for this domain has to handle "the answer
requires combining two clauses" as the normal case, not the edge case.

---

## Step 2 — The retrieval tool

The `mcp_servers` dict-vs-list confusion and the `allowed_tools` naming mismatch are both classic
"wrong shape of config, no error message" problems — a recurring pattern in SDK-based agent
development generally, not specific to this SDK. When a tool silently isn't available, the debugging
instinct should be to check the *wiring* (server registration, permission strings) before assuming
the *prompt* is the problem, since a missing tool and an unused tool produce identical-looking
symptoms from the outside — the agent just doesn't do the thing.

The `BUILTIN_LOCKDOWN` list is worth dwelling on conceptually: Claude Code ships with a broad set of
general-purpose tools (file system, shell) because it's designed as a coding agent. Repurposing the
same SDK for a customer-facing agent means those tools are pure liability with zero customer value
— there's no legitimate reason a CX agent needs shell access. This is the least glamorous kind of
guardrail (an allowlist), and also the most load-bearing one, because it doesn't depend on the model
behaving well — it removes the capability entirely.

---

## Step 3 & 4 — The grounding failure and its fix

The underlying mechanism worth understanding here: an LLM's default behavior, absent instruction, is
to answer from its parametric knowledge (what it learned during training) rather than to defer to
retrieved context — even when a retrieval tool is sitting right there. This isn't a flaw specific to
Claude or this SDK; it's a general property of how these models are trained, since most of their
training data consists of directly-answering questions rather than deferring to external sources.
Grounding has to be actively engineered in via the system prompt (and reinforced by the tool
description) — it is not the model's default posture.

A common misconception worth heading off: trainees sometimes read the fixed system prompt and
conclude "so now it always uses the KB and is always right." Grounding forces the model to *use*
retrieval and *cite* what it retrieved — it does not fix retrieval quality itself. If `search()`
returns the wrong clause with high confidence, a well-grounded agent will confidently cite the wrong
clause. Grounding and retrieval quality are separate concerns that solve separate problems, and
Lab 1 only addresses the first one directly (the KB is small and curated enough that retrieval
failures are unlikely to surface).

---

## Step 5 — Persona & tone

This is the second newly-added section. It exists because "persona & tone" was a named post-lunch
topic in the day's topic index but had no corresponding notebook content at all before this
revision — not a thin treatment, an actual gap. The fix reuses the existing prompt-chaining pattern
(`persona_options` extends `grounded_options.system_prompt`) rather than introducing a new
mechanism, specifically so trainees don't have to learn a second way of shaping agent behavior on
top of the one they just used for grounding.

**The one-sentence version of what this step teaches:** grounding and persona are orthogonal axes,
and conflating them is a common early mistake. A trainee debugging a bad response should be able to
ask two separate questions in order — "is this factually wrong?" (grounding/retrieval problem,
Steps 1–4) then "is this tonally wrong?" (persona problem, this step) — rather than one blurred
question "why is this answer bad?" that doesn't point at which system prompt clause to fix.

**Why this section is deliberately light on code and heavy on a side-by-side read:** there's no new
tool, no new failure mode to engineer, no new assertion to check — the entire teaching moment is
"read two outputs for the same question and notice what changed." That's intentionally the
lightest-weight step in the notebook. Resist the urge to add more mechanism here (e.g., a
persona-switching tool, multiple persona variants to compare) — the point is narrow and the current
scope matches it. If trainees want to go further, the natural extension is "try writing your own
persona clause and see how far you can push tone while grounding stays intact," which needs no new
notebook cells, just a prompt to trainees.

**The forward reference to Day 4 (policy-as-config) is worth spending thirty seconds on live,** for
the same reason the Lab 1 system-prompt-chaining aside is worth spending time on: it heads off the
"is this how you'd actually do it in production" question before it's asked, and the honest answer
here is structurally identical to that one — the *concept* (persona as a first-class, swappable
input) is real, the *hardcoded string* is a teaching simplification.

**One failure mode worth watching for live:** because `persona_options` is built by appending to
`grounded_options.system_prompt`, if a trainee edits `grounded_options` after this point and
re-runs only this cell, the persona instructions land on stale grounding text. This is the same
"re-run top-to-bottom" caution that already exists for the escalation/action/instrumentation chain
(see below) — Step 5 is simply the first place in the notebook where it starts to matter, since
it's the first step built by extending something earlier rather than writing a fresh prompt.

---

## Step 6 — Containment & Escalation

Renamed from "Step 5 — Escalation" in this revision, with containment named explicitly as the other
half of the same design decision, because "containment" was a named post-lunch topic with no
matching vocabulary anywhere in the original notebook — escalation was taught, but never framed as
one side of a contain-vs-escalate choice the agent (and its designer) is making on every turn.

**Why this is a rename-plus-reframe rather than new content:** everything Steps 1–5 already build
*is* containment — a grounded, on-persona answer that fully resolves the question without a human
is exactly what "contained" means. There's no new code needed to teach containment as a concept;
what was missing was naming it, so that when trainees later hit a case where the agent *should* have
answered on its own but escalated instead (over-escalation) or answered when it shouldn't have
(Step 3's failure mode, re-framed here as over-containment), they have the vocabulary to describe
which failure they're looking at instead of just "the agent got it wrong."

**A framing worth using live if trainees seem to treat escalation as strictly safer than
containment:** it isn't, categorically. Over-escalating has a real cost — the customer waits for a
human for something the agent could have handled cleanly, and every unnecessary handoff is load on
a support team that resolution agents are supposed to reduce, not shift the timing of. The
Deflection vs. resolution concept from the morning session is the same tension one level up:
just as "conversation ended" isn't the same as "problem solved," "escalated" isn't automatically the
responsible choice — it's the responsible choice exactly when containment genuinely isn't
appropriate, and not by default.

The system-prompt-chaining pattern (`escalation_options` = `grounded_options.system_prompt` + more)
is a common, reasonable way to build up agent behavior incrementally across a lab — but it's worth
naming the tradeoff explicitly: it's readable and demonstrates incremental capability well in a
teaching context, but it's fragile to edits. In a real codebase, this pattern usually gets replaced
by composing prompt *sections* from named constants or a template, specifically so that changing
one section doesn't require re-deriving every downstream variable by hand. Worth mentioning if
anyone asks "is this how you'd actually do it in production" — the answer is: the concept
(cumulative instruction layers) is real and used, the string-concatenation mechanism is a teaching
simplification.

On escalation quality: a useful mental test for "is this a good escalation" is whether a human
picking up the ticket cold, with zero other context, could act on it immediately. A summary like
"customer asked about coverage" fails that test; a summary like "customer POL-5521 asked whether
knee surgery is covered under an auto policy — out of scope for this KB, no relevant clause exists"
passes it. This is the same standard a support team would hold a human agent to, and there's no
reason to hold an AI agent to a lower one.

---

## Lab 2 — Idempotent actions with an approval gate

Two distinct properties are being taught together here, and they're worth being able to separate
when asked:

- **Confirmation-gating** — the tool refuses to take effect until an explicit, separate approval
  step has happened. This protects against the agent (or a manipulated conversation) taking a
  consequential action based on a misread of what the customer actually wants.
- **Idempotency** — repeating the *same* logical operation (identified by a stable key) doesn't
  repeat its effect. This protects against a completely different failure class: retries, network
  hiccups, or an agent that (for whatever reason) calls the same tool twice for what it believes is
  the same customer intent.

Both matter independently. A confirmation gate without idempotency is still vulnerable to duplicate
claims on retry. Idempotency without a confirmation gate would happily and safely re-execute the
*wrong* action exactly once. The lab combines them because real action tools — filing a claim,
blocking a card, issuing a refund — need both simultaneously.

The two-turn test (cell 15/16) is the part of this lab that's easy to under-value: it's tempting to
treat the offline `.handler()` check as sufficient because "the logic obviously works, I read the
code." The reason the agent-driven test exists separately is that the interesting failure mode
isn't in the Python logic at all — it's in whether the *model* correctly tracks and reuses a value
it generated itself, across a conversational turn boundary, without being reminded. That is a
capability of the agent, not of the tool, and no amount of unit-testing the tool catches it.

---

## Lab 3 — Instrumentation

The distinction between `resolved` and `escalated` and `failed` is doing more conceptual work than
it might first appear. It's a direct, code-level encoding of the "deflection vs. resolution"
concept from the morning session — a metric that's easy to game (call everything "handled") and
hard to hold an agent honestly accountable to (actually check whether the customer's problem got
fixed).

`failed` is the case that resists a tidy definition, and that's realistic rather than a gap in the
lab: production CX systems genuinely struggle to define "failed" cleanly, because most failure
paths get papered over by routing to a human (which then counts as `escalated`, technically true
but hiding the fact that the agent couldn't help at all). A cleaner way to frame it for anyone who
gets stuck: `escalated` means "a human can pick this up and continue productively"; `failed` means
"the agent could not identify or attempt a productive next step, escalation or otherwise." The
`cancel_policy` example works as a `failed` case because there's genuinely no tool and no
well-scoped handoff path defined for it — not because it's an unusual request, but because this
agent's toolset simply wasn't built to handle it.

The in-process nature of `create_sdk_mcp_server` (the tool call *is* a direct Python function call,
not a network round-trip to a separate service) is worth flagging as a simplification specific to
this lab's local setup — in a production deployment, MCP servers are frequently separate processes
or services, and the same tool call becomes a real network call with its own latency and failure
modes. The programming model looks identical either way, which is part of MCP's value, but "looks
identical" is not "behaves identically under load or network partition."

---

## Cross-lab thread worth surfacing at the end

All three labs, underneath their surface topics (retrieval, actions, instrumentation), are teaching
one shared discipline: **don't trust an agent's self-report of its own success.** A citation has to
be checked against the actual clause. A confirmation flow has to be verified by watching the agent
drive it, not by trusting the tool logic in isolation. A `resolved` log entry has to be checked
against whether the underlying problem was actually fixed. This is the throughline worth naming
explicitly if trainees seem to be treating the three labs as unrelated exercises rather than three
angles on the same discipline.
