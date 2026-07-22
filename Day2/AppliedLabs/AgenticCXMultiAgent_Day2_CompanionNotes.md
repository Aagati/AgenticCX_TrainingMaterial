# Day 2 — Post-Lunch Applied Lab: Companion Notes

**Notebook:** `AgenticCXMultiAgent_Day2AL.ipynb` · **Lanes:** Insurance (Lab 1) · Banking (Lab 2) · Retail (Lab 3) · **Duration:** 4h

Same convention as Day 1's companion notes: the notebook carries the walkthrough, this document
goes one layer deeper — the reasoning, misconceptions, and production context behind each lab,
organized the same way the notebook is.

---

## Why three lanes today, not one

Day 1 ran all six post-lunch topics through a single Insurance agent, extended step by step. Today
deliberately doesn't do that — each lab lives in a different vertical (Insurance, Banking, Retail),
matching `contents.md`'s lab mapping exactly. The reason isn't variety for its own sake: routing,
memory, and assist are each easiest to see cleanly in a domain that isn't already carrying the
weight of five other concepts. Trying to bolt a supervisor, a memory layer, *and* an assist mode
onto Day 1's single Insurance agent would have made it hard to tell, when something broke, which of
the three new mechanisms was actually at fault. Three lanes, one mechanism each, is a deliberate
debugging-clarity choice, not a content-padding one.

The trade-off worth naming out loud if asked: this means Day 2, unlike Day 1, doesn't give trainees
a single agent that visibly accumulates all six capabilities in one place. If a trainee wants to see
what a supervisor + memory + assist agent looks like *combined*, that's explicitly capstone
territory (Day 5), not something today's notebook hands them pre-built.

---

## Setup

Nothing new environment-wise — same CLI/SDK/API-key prerequisites as Day 1. The one addition is
importing `AssistantMessage` and `TextBlock` directly, which Day 1 never needed because `ask()`
just printed whatever came back. Today's supervisor pattern (Lab 1) needs to *capture* a
specialist's final answer as a plain string to hand back as a tool result, which means reaching
into the message stream and pulling text out deliberately, not just printing it.

**Worth confirming live, quickly, before Lab 1:** ask a trainee to predict what happens if
`_run_specialist` prints the raw `message` objects instead of filtering for `AssistantMessage` +
`TextBlock`. The honest answer is "it still mostly works for demo purposes, but the returned string
now has repr-formatted junk in it instead of clean text" — a good moment to make the point that
*which* SDK message types matter depends entirely on what you're going to do with the output next.
Day 1's `ask()` didn't care because it only ever printed for a human to read. Lab 1 cares a lot,
because the string becomes a `tool_result` another model has to parse and reason about.

---

## Architecture — the "specialist is just an agent" idea

This section exists for the same reason Day 1's architecture section did: naming all the moving
pieces once, before Lab 1 needs them, so debugging can point back at a diagram instead of explaining
the whole idea from scratch mid-lab.

**The single idea worth landing hard, because everything else in Lab 1 follows from it:** a
"specialist agent" is not a new SDK primitive. It's an ordinary `ClaudeAgentOptions` +
`ClaudeSDKClient`, identical in kind to every agent built on Day 1 — the only thing that changed is
*where it gets invoked from*. Yesterday, test code called `ask(options, question)` directly. Today,
a `@tool`-decorated function calls the exact same shape of thing, and that function is itself
wired into a different agent's `allowed_tools`. If a trainee walks away thinking "multi-agent
requires some fundamentally different mechanism," that's the misconception to catch and correct
immediately — the mechanism is identical, only the caller changed.

**On naming `ClaudeAgentOptions.agents` (the SDK-native subagent field) without using it:** this
SDK version genuinely ships a built-in mechanism for exactly this pattern — named subagents wired
into the CLI's own dispatch tool. Building Lab 1 on top of it directly would be the shorter path,
since it's the "real" production mechanism. The manual version is used instead for the same reason
Day 1 named `permission_mode` and `hooks` without using them: naming a capability and deferring it
teaches something a silent shortcut doesn't. A trainee who's manually wired `ask_claims_specialist`
as a tool and watched `_run_specialist` open a nested session understands *why* a dispatch tool
works, not just that one exists to call. If a trainee asks "why not just use `agents=`" live,
that's a good sign they're already thinking at the right level — the answer is exactly the sentence
above: the concept is real and built into the SDK, the manual version is what makes the mechanism
visible before the shortcut hides it again.

**Why the supervisor has zero domain tools, not "domain tools plus a routing preference":** this is
the same guardrail move as Day 1's `BUILTIN_LOCKDOWN` — a capability the supervisor doesn't have
can't be misused, no matter how well- or poorly-worded its system prompt is. If `kb_search` were
also on the supervisor's `allowed_tools` list, Step 3's failure demo would be *less* reliable, not
more interesting — the supervisor would have an easy escape hatch (answer it myself) available even
after Step 4's fix tightens the prompt. Removing the capability entirely is what makes routing a
structural property of the agent rather than a probabilistic outcome of good prompting.

---

## Lab 1 — Supervisor + two specialists (Insurance)

### Step 1 & 2 — Reusing Day 1's KB, and why CLM-1077 is built the way it is

Reusing yesterday's `policy_chunks` and `kb_search` verbatim is a deliberate continuity beat, not
laziness — it lets you say, out loud, "yesterday this KB was the *entire* agent's knowledge; today
it's one specialist's tool," which is a concrete, checkable illustration of what "splitting into
specialists" actually buys you: yesterday's single agent had no real data source for claim-status
questions at all and would have had to either refuse or (worse) guess. Today, that gap gets a real
specialist instead of staying a gap.

`CLM-1077` is the pedagogical core of Lab 1, playing the same role POL-4.2/POL-9.1 played on Day 1:
it's a realistic case that requires combining two sources to answer completely. The claim is denied,
and the *reason* for the denial is a policy rule (POL-2.5's 7-day window) that lives in a completely
different specialist's knowledge. A trainee who only tests single-domain questions (a plain claim
status, a plain coverage question) will conclude Lab 1 works and never discover whether synthesis
across specialists actually functions — walking through the CLM-1077 case live is not optional if
the goal is to actually validate the "supervisor" part of "supervisor + specialists," not just the
"specialists" part.

### Step 3 & 4 — The routing failure, and why "both tools were called" is the real check

The failure mode here is structurally identical to Day 1's grounding gap (a capable tool sitting
unused because nothing mandates it), which is worth saying explicitly if a trainee seems to think
Day 2 introduced a brand-new category of problem. It didn't — it's the same lesson, applied one
level up the stack: yesterday, an available tool went uncalled because the system prompt didn't
require it; today, an available *specialist* goes uncalled for the same reason.

**The most common thing to get wrong when checking Step 4's fix:** reading only the final answer
text and pattern-matching it against "sounds right." A supervisor that calls only
`ask_claims_specialist`, gets back the denial and a generic guess about "typical filing windows,"
and stitches that into a plausible-sounding sentence can produce an answer that *reads* complete
without ever having called `ask_policy_specialist` at all — same failure shape as Day 1's "citation
present but wrong clause," one level removed. The only reliable check is watching (or logging) which
tools actually fired, not evaluating the prose. Worth demonstrating live: run the CLM-1077 question
and count tool calls out loud before reading the answer.

---

## Lab 2 — Memory across a channel switch (Banking)

This is the lab to spend the most live time on, since it's the day's stated ship line
(`contents.md`: "a multi-agent CX system with persistent memory across at least two channels") — if
a trainee leaves without a working, *demonstrated* version of this, the day hasn't shipped what it
promised, regardless of how Labs 1 and 3 went.

### Step 5 — Why episodic and semantic memory are different tools, not one

The distinction is easy to state and easy to blur in practice, so it's worth a concrete test
question to keep it sharp: "did this happen" is episodic; "what's generally true about this
customer" is semantic. The repeat-disputer fact at the end of Lab 2 is the clearest illustration —
it's explicitly *derived by looking across* three episodic entries, not a fourth one. A trainee who
implements semantic memory as "just another kind of log entry with a different tag" has missed the
point: the value of a semantic fact is that something (a routing decision, a risk model, a future
conversation) can read it in constant time instead of re-scanning and re-deriving the pattern from
raw history every single time.

**A misconception worth heading off proactively:** trainees who've used long-context models before
sometimes assume "the model can already remember things pretty well within a big context window, why
do we need explicit memory tools?" The honest answer has two parts. First, and most relevant to
today's lab: a `ClaudeSDKClient` session's context does not survive to a *new* session — and a
channel switch is very often exactly that, a new session, sometimes on a different backend
entirely. No amount of context-window size helps once the session itself has ended. Second, even
within a single long session, unstructured context is worse than a queryable fact store for the
specific job semantic memory does — finding "is this customer a repeat disputer" by re-reading a
long transcript is strictly worse than reading one fact.

### Step 6 — The amnesia demo, and what actually proves the fix worked

**The failure has to be produced with a genuinely new `ClaudeSDKClient`, not a fresh `.query()` call
on the same client.** This is the easiest way to accidentally invalidate the whole lab: if session 2
reuses session 1's client object, the model still has session 1's turns in its own context window
regardless of whether `recall_context` ever gets called, and the "fix" in the next cell will appear
to work even with the weak prompt, because the failure was never real to begin with. Confirm, before
running Step 6, that the two `await ask(...)` calls really do use two separate `ClaudeSDKClient`
lifetimes (they do, because `ask()` opens and closes its own client each call) — this is subtle
enough to be worth walking through the `async with ClaudeSDKClient(...)` line by line if anyone
looks confused about why session 2 doesn't just "already know."

**What a passing fix actually needs to show, and what's an easy false positive:** it is not enough
for session 2 to avoid asking "what dispute?" — a model can produce a vague, hedging non-repeat
question ("could you remind me which dispute you mean?") that technically isn't a request to
start over, without ever having called `recall_context` at all, just from general conversational
smoothing. The real check is whether session 2's response contains the *specific* recalled detail —
the $45 amount, or "card ending 9931" — because that detail could only have come from
`memory_store`, not from the model's general knowledge or conversational instincts. Grading on
"didn't ask a redundant question" instead of "surfaced the actual recalled fact" is a real risk of
this checkpoint passing when it shouldn't.

### The channel adapters — deliberately thin, on purpose

`chat_adapter` and `sms_adapter` doing almost nothing is not an oversight to apologize for; it's the
same choice Day 1 made with `score()` standing in for real retrieval. The entire teaching point of
"channel adapters" as a concept is the *normalization contract* — every channel's input becomes the
same `{user_id, channel, text}` shape before anything downstream touches it, so the agent and the
memory tools never have to special-case a channel. Naming, explicitly, what a real adapter would
also do — auth, per-channel rate limits, SMS length constraints, mapping a platform user id to an
internal one — is worth doing out loud specifically so trainees don't walk away thinking today's
two-line functions are what a production adapter looks like. The mechanism (normalize, then forget
which channel it came from) is real; the thinness is the simplification.

---

## Lab 3 — Agent-assist + a QA hook the agent can't touch (Retail)

### Step 7 — "Agent-assist" is a prompt contract, not new architecture

This is arguably the single most important reframe in today's material, and worth stating plainly,
more than once, live: **nothing about the underlying mechanism changes between a resolution agent
(Day 1), a routed specialist (Lab 1), and an assist-mode draft (this lab).** Same grounding pattern,
same `kb_search`-and-cite discipline. The only thing that changed is the system prompt's framing of
*who the output is for* and *what happens to it next* — a resolution agent's output goes straight to
the customer; an assist-mode agent's output goes to a human first. If a trainee builds their own
capstone assist surface by inventing a new tool-calling architecture instead of just changing the
prompt's audience and adding a confidence line, that's a sign this reframe didn't land — it's worth
checking for directly rather than assuming it's obvious.

**On self-reported confidence, and why it's flagged as a real limitation rather than treated as a
solved problem:** a model stating "Confidence: high" is not a calibrated probability — it's a
plausible-sounding string produced the same way the rest of its output is. It's genuinely useful as
a *triage* signal (route low-confidence drafts to more careful review), and genuinely risky if
treated as a trustworthy metric on its own. This is exactly the setup for why Step 8's hook exists
externally: self-reported confidence and self-reported outcomes share the same weakness, and the fix
in both cases is the same — check against what actually happened, from outside the agent.

### Step 8 — Why `log_assist_review` is not a `@tool`, and why that's the actual lesson

This is a direct, structural contrast with Day 1 Lab 3's `log_outcome`, and it's worth drawing that
contrast explicitly rather than letting it pass as an implementation detail. Day 1's `log_outcome`
was self-reported: the agent decided, at the end of its own turn, whether it had resolved, escalated,
or failed — and Day 1's companion notes already flagged the risk in that (a `resolved` log entry
that just means "the agent produced an answer," not "the problem got fixed"). Lab 3 removes that
risk category entirely by construction: `log_assist_review` is a plain Python function that is never
wired into any `ClaudeAgentOptions.allowed_tools`. The agent has no way to call it, see it, or
influence what it records, because the agent's involvement in the process ends the moment it
produces a draft.

**The generalizable claim, worth stating once clearly:** a hook that instruments a human or system
*action* is structurally harder to spoof than a hook the agent calls on itself, because the agent
was never in the room for it. This is the actual definition of "QA hooks" this lab is teaching — not
"a place where logging happens," but "logging wired to the event that's actually trustworthy,"
which for an assist surface is the human's decision, not the agent's opinion of its own draft. A
trainee who reimplements this as another agent-callable tool (e.g., asking the agent to report
whether its own draft was good) has rebuilt Day 1's self-report problem inside what was supposed to
be the fix for it — worth watching for, and worth naming directly if it happens, since it's an easy
trap precisely because it "still technically logs something."

**Where the enforcement actually has to live, and what this lab does *not* claim to have built:**
nothing in Lab 3's code prevents a badly-built application from sending an assist draft straight to
a customer without ever routing it through a human review step — the "never sent directly" guarantee
is a prompt convention today, not a code-enforced gate the way Lab 2's approval-gated `file_claim`
from Day 1 was structurally enforced. Worth naming this gap directly rather than letting the parallel
to Day 1's idempotent-actions lab suggest a stronger guarantee than actually exists here: the actual
gate — routing a draft to a real human queue instead of a customer-facing channel — lives entirely in
the surrounding application, which this lab doesn't build. That's legitimately out of scope for a
4-hour lab; it's not out of scope to say so.

---

## Cross-lab thread worth surfacing at the end

All three labs, underneath their surface topics (routing, memory, assist), are teaching one shared
discipline: **state has to survive a handoff, and something has to verify it actually did — not
assume it did because the demo looked fine.** A supervisor's routing has to be checked by which
tools fired, not by reading fluent prose. A memory fix has to be checked by the specific recalled
detail surfacing in session 2, not by the absence of an awkward re-ask. An assist draft's quality has
to be checked by a hook outside the agent's control, not by the agent's own confidence line. This is
the same throughline Day 1 closed on ("don't trust an agent's self-report of its own success"), one
level up: today it's not just the agent's self-report that needs external verification, it's the
handoff itself — to another agent, across a session boundary, or to a human — that needs to be
checked rather than assumed.
