# Day 3 — Post-Lunch Applied Lab: Companion Notes

**Notebook:** `AgenticCXVoice_Day3AL.ipynb` · **Lanes:** Insurance (Lab 1) · Banking (Lab 2) · Telecom (Lab 3) · **Duration:** 4h

Same convention as Day 1/2's companion notes: the notebook carries the walkthrough, this document
goes one layer deeper — the reasoning, misconceptions, and production context behind each lab.

---

## Why voice needed a different verification bar, and what that bar actually was

Day 1 and Day 2 ran every cell against a real, authenticated Claude session — no key needed
because this environment's Claude Code CLI login covers it. Voice breaks that: Pipecat and
LiveKit both talk to Deepgram/Cartesia/Anthropic/AssemblyAI directly over the network, and there
is no microphone, speaker, or phone line in this sandbox regardless of keys. Rather than either
(a) faking a "live call" with mocks dressed up to look real, or (b) quietly downgrading to
import-only checks and calling it a day, this notebook drew an explicit **three-tier line** and
built to it: Tier A (runs for real here, no key), Tier B (real code, needs a trainee's own key),
Tier C (needs a real phone line, cannot run in any notebook).

**What actually ended up Tier A surprised us, and that's worth saying out loud in the session:**
going in, the expectation was that voice would be mostly Tier B/C — most of the "real" work
happens over a network to a paid provider. What the actual installed packages turned out to
contain: Silero VAD's ONNX model bundled directly inside `pipecat-ai` and loadable inside
`livekit-agents` plugin code with zero keys; a second bundled model (Smart Turn v3) that
Pipecat's context aggregator loads automatically; `ServiceSwitcher`'s failover logic testable by
constructing real service objects and driving them with a real `ErrorFrame`; a WER-based quality
gate that's real math regardless of where the transcript came from; and — the most fully testable
of the three labs — an entire compliance state machine that has no network dependency at all,
because compliance logic was never actually a voice-technology concern, it's a call-flow-logic
concern that happens to sit in a voice product. The honest lesson for anyone building on top of
a fast-moving framework: read the installed source before assuming what's live-only.

---

## Setup

**The `ANTHROPIC_API_KEY` gotcha is the single most likely thing to trip someone up live**, and
it's worth walking through slowly rather than assuming the callout in the notebook is enough:
Day 1 and 2's `claude_agent_sdk` shells out to the Claude Code CLI, which can be authenticated
via `claude login` (an OAuth-style flow) *or* a raw API key — either works, because the CLI
handles the auth negotiation. Pipecat's `AnthropicLLMService` and LiveKit's `anthropic.LLM`
plugin do not go through the CLI at all; they call the Anthropic Messages API directly using
the `anthropic` Python SDK, which only understands a raw `ANTHROPIC_API_KEY` environment
variable. A trainee who's been happily running Day 1/2 via `claude login` and has never set the
raw env var will get a clean, confusing auth failure here — worth pre-empting verbally before
anyone hits it.

**Why the install section spends a paragraph on what's *not* needed:** most trainees' mental
model of "installing a voice stack" involves chasing down SDKs for every vendor named in the
tech-stack table. Pipecat's actual footprint is much lighter than that mental model predicts —
it implements Cartesia, ElevenLabs, and AssemblyAI itself over raw `aiohttp`/`websockets`
rather than depending on each vendor's official SDK, and Deepgram/Anthropic are the only two
extras that pull in a real separate package. This is worth naming explicitly because it
contradicts the intuitive assumption, and a trainee who assumes otherwise will spend time
hunting for packages that were never going to be installed as separate dependencies.

---

## Lab 1 — Insurance: pipeline assembly + latency engineering

### Why the "weak → fix" beat couldn't be a live failure demo this time

Every other lab this week (Day 1's ungrounded agent, Day 2's non-routing supervisor) demonstrated
its failure mode by actually running the weak version and watching it produce a visibly wrong
answer. That pattern depends on being able to run something live, which this sandbox can't do for
voice. The fix here was to reframe the "weak" configuration around **real, documented Pipecat
settings** rather than an invented "blocking" antipattern — Pipecat's architecture is inherently
frame-streaming, so constructing something that actually blocks the way Day 1's `weak_options`
answered from parametric memory would mean fighting the framework's own design, which isn't a
realistic mistake anyone would actually make. `interim_results=False`, `TextAggregationMode.SENTENCE`,
and no VAD are each individually defensible choices a team might make without thinking about
latency — that's the actual, realistic failure mode being taught: not "someone did something
obviously wrong," but "a set of individually-reasonable defaults compound into a bad number."

**A misconception worth heading off:** a trainee might read the weak/fixed contrast and conclude
`interim_results=True` and `TextAggregationMode.TOKEN` are simply "the right settings, always."
They're a latency/quality tradeoff, not a universal improvement — Pipecat's own docstring for
`TextAggregationMode.TOKEN` names the cost directly ("may affect speech quality depending on the
TTS provider"). The lesson is "know the tradeoff and choose deliberately for your latency
budget," not "always pick the faster-sounding option."

### The `SileroVADAnalyzer.set_sample_rate()` gotcha, and why it's worth dwelling on live

This is a genuinely easy trap, not manufactured for teaching purposes — it was hit for real while
building this notebook. `SileroVADAnalyzer(sample_rate=16000, ...)` looks like it should fully
configure the analyzer; the constructor accepts and stores the value, but the actual internal
`_sample_rate` used by `voice_confidence()` stays `0` until `set_sample_rate()` is called
separately. In a real pipeline this happens automatically — the transport calls it once it knows
the actual negotiated stream rate — which is exactly *why* the constructor doesn't just use the
passed value directly: the transport is the actual source of truth for sample rate, and the
constructor argument is a hint, not a guarantee. Any standalone code that constructs a
`SileroVADAnalyzer` outside a running pipeline (exactly what this notebook's Tier A test does)
has to replicate that one missing step by hand. Worth a live moment: ask trainees what class of
bug this is — it's the same shape as a config object that "looks complete" but has a required
initialization step buried in a different layer of the system, a pattern that shows up constantly
in frameworks with implicit runtime wiring.

### What the VAD benchmark actually proves, and what it doesn't

The measured real-time factor (on the machine this was built on: ~55x — a real number, reproduce
it and expect a different one on different hardware) proves the VAD stage's own processing
overhead is negligible relative to a voice-to-voice budget of even a few hundred milliseconds.
It says nothing about STT/LLM/TTS network latency, which dominates the real budget by roughly two
orders of magnitude. If a trainee walks away thinking "VAD is the bottleneck to optimize," that's
a miscalibration worth correcting directly — VAD is the one stage of this pipeline that was never
actually a latency risk; it's on the table specifically *because* it's the one number this
sandbox could produce honestly, not because it's the most important one.

### On the latency budget table mixing real and estimated numbers

This is the section most likely to get pushback along the lines of "isn't this just guessing with
extra steps?" The honest answer: no, because the table is explicit, row by row, about which
numbers are real and which are representative, and the representative ones are sourced from the
library's own documentation (the Cartesia aggregation-mode cost) rather than invented. The
alternative — presenting a single, unlabeled "our agent is under 800ms" claim built partly on
guesses — is exactly the "confident, uncited, wrong" failure Day 1 spent Step 3 warning about,
just relocated from a coverage question to a performance claim. The discipline transfers
directly: a number is only as trustworthy as its citation, whether that number is a policy clause
or a latency figure.

---

## Lab 2 — Banking: reliability (STT failover) + voice eval & QA (WER gate)

### `ServiceSwitcher` — a case where the framework already had the pattern

Worth naming as a genuinely good find, not just a lucky one: Day 2's Lab 2 (idempotent actions)
had to be hand-built, because the Claude Agent SDK has no built-in approval-gate primitive.
Pipecat, by contrast, ships `ServiceSwitcher` + `ServiceSwitcherStrategyFailover` as an explicit,
documented, first-class mechanism for exactly this pattern — its own docstring even gives the
intended usage shape verbatim. The lesson worth drawing out live: **check whether the framework
already has the pattern before hand-rolling it.** Day 2 hand-built idempotency because it had to;
Lab 2 here uses the framework's own primitive because it exists and is more idiomatic than
reinventing it. Knowing which situation you're in is itself a skill.

### The async event-handler timing gotcha

A second real bug hit while building this notebook, and a genuinely instructive one:
`switcher.strategy.event_handler("on_service_switched")` registers an `async def` handler, and
Pipecat's event dispatch (in `BaseObject._call_event_handler`) schedules async handlers via
`asyncio.create_task(...)` — fire-and-forget, not awaited inline. The first version of this test
checked `switch_events` immediately after `handle_error()` returned and failed, even though the
underlying switch had genuinely happened (the active-service check passed; only the event-handler
assertion failed). The fix — `await asyncio.sleep(0.01)` before checking — is a small thing
syntactically but points at a real category of bug: **event-driven systems can be correct in
their eventual state while still failing an assertion written as if everything were synchronous.**
This is worth connecting explicitly to real production debugging: a "the event handler never
fired" bug report is very often actually "the event handler fired one tick later than the
assertion checked," and those two bugs have completely different fixes.

### What the WER gate is actually teaching, separate from the specific numbers

The `wer_gate()` function is the actual reusable artifact here — real `jiwer.wer()` computation,
a real threshold, real pass/fail logic. The three example hypotheses feeding it are clearly
labeled representative, and that label matters more than it might first appear: a trainee's
instinct might be to treat "WER = 0.143" as itself a meaningful fact about Deepgram or
AssemblyAI's real accuracy. It isn't — it's a demonstration of the *mechanism*. The actual
verdict on "is my fallback provider good enough" only exists once a trainee runs this same gate
against real transcripts from their own keys (Tier B). Emphasize the gate, not the sample numbers,
if trainees start quoting the demo WER values as if they were real accuracy benchmarks.

---

## Lab 3 — Telecom: telephony + compliance

### Why this is the most fully-verified lab of the three, and why that's not an accident

Telephony (SIP, a real phone line) is the single most Tier-C-locked piece of the entire day — and
yet Lab 3 as a whole ended up the most thoroughly, honestly Tier-A-tested lab, including a
rejected-bypass scenario and independent audit-log replay. The reason is structural, not lucky:
"compliance" was never actually a voice-technology problem being solved by Deepgram or Cartesia —
it's a call-flow state-machine problem that happens to sit in front of a voice product. Once that
reframe is made, the entire thing becomes plain Python with zero network or audio dependency.
Worth stating directly if a trainee assumes "telephony lab" means "the least testable lab" — the
telephony *transport* is Tier C; the telephony *lab's actual content* (the compliance logic) is
almost entirely Tier A, and those are different claims.

### The structural-gate pattern, called back to Day 1 explicitly

`CompliantCallFlow`'s `recording_active` can only become `True` by passing through
`on_consent_response(granted=True)` — there is no other method, no other code path, that sets it.
This is the identical shape of guarantee as Day 1's `file_claim`: a prompt asking an LLM to "get
consent before recording" is a request that can be forgotten, misread, or overridden by a
sufficiently unusual conversation; a state machine with no transition to `RECORDING` from
anywhere except `CONSENT_GRANTED` cannot be bypassed by a bad LLM turn, because the LLM was never
given the authority to reach that state directly. The `on_consent_response()` bypass-attempt test
(calling it before `on_connect()`) exists specifically to demonstrate this isn't just true in the
happy path — the guarantee holds even under a deliberately out-of-order call.

**A framing worth using live if a trainee asks "but couldn't a bad LLM just claim it got
consent":** yes, if consent-tracking were left to the LLM's own judgment about the conversation.
That's exactly why it isn't — `on_consent_response(granted=...)` is called by the surrounding
application logic (the actual caller's yes/no, however that's captured — DTMF, a keyword match,
a structured tool call the LLM invokes only after genuinely hearing an answer), not inferred by
the LLM deciding on its own that consent was probably given. The state machine's guarantee is
only as strong as what's allowed to call `on_consent_response(True)` — worth a beat of discussion
on where in a real system that call would actually originate.

### Replayability, and its connection to Day 2's QA hook

`replay_final_state()` deliberately never touches the live `CompliantCallFlow` object — it
reconstructs a call's compliance status from `audit_log` alone. This is the same "verify from
outside, don't trust self-report" discipline as Day 2 Lab 3's `log_assist_review` (never called
by the agent, only by the surrounding application), applied one level up: here it's not just that
the *logging* is external to the agent, it's that the entire *verification of compliance* has to
be reconstructable by someone (a regulator, an auditor, a customer dispute) who has only the log
and none of the original running system. A "replayable audit trail" that actually requires
trusting the system that produced it isn't replayable in any sense that matters for governance.

---

## Appendix — LiveKit Agents

### The real architectural contrast, not just a syntax difference

Pipecat's `Pipeline([...])` and LiveKit's `Agent(stt=..., llm=..., tts=..., vad=...)` aren't two
spellings of the same thing — they represent a genuine design fork in how much pipeline structure
the framework versus the developer owns. Pipecat trades more code for more visibility and control
(you can insert a custom `FrameProcessor` anywhere in the list, reorder stages, build things
Pipecat's authors never anticipated). LiveKit trades that flexibility for less code and an
implicit, framework-owned pipeline order. Neither is strictly better — the choice matters most
when a project needs to do something the framework didn't anticipate, which is exactly when
Pipecat's explicitness pays for itself, or doesn't come up at all, which is exactly when LiveKit's
brevity wins with no downside.

### Why Silero VAD loading for real (unlike STT/TTS/LLM construction) is worth pointing out live

`lk_silero.VAD.load()` is not just object construction the way `lk_deepgram.STT(api_key=...)` is
— it's an actual model load, and it succeeded with zero keys, same as Pipecat's bundled Silero
model. This is worth flagging specifically because it reinforces Lab 1's VAD-benchmark point from
a second, independent framework: **VAD is consistently the one piece of the voice stack that
doesn't depend on a paid API**, across frameworks, not just a quirk of Pipecat's packaging choice.

### The genuine limit, and why it's narrower than an earlier draft of this notebook claimed

An earlier draft of this appendix said LiveKit's own test helper
(`livekit.agents.testing.fake_job_context`) "still requires a real `rtc.Room` connection" —
that's wrong, checked directly against the installed `livekit-agents==1.6.6` source. Its
signature is `fake_job_context(*, room: rtc.Room | None = None, ...)`; the docstring's example
happens to show a connected room, but that's one usage, not a requirement — when `room` is
omitted it constructs a fresh, unconnected `rtc.Room()` internally and stubs `_connected = True`
specifically so context construction works with zero live connection. The real, structural limit
sits one layer up: a genuine end-to-end audio turn (audio actually flowing in and out) still needs
a real connected room, in either framework. What's narrower than the earlier draft implied is
context/session *construction* — `fake_job_context()` plus `AgentSession`/`Agent` assembly is
plausibly runnable further into Tier A/B territory than "Tier C, full stop." A trainee comparing
the two frameworks for local/offline testability should weigh the precise boundary (construction
vs. a live audio turn), not a rounded-up "LiveKit always needs a connection, Pipecat never does."

---

## Cross-lab thread worth surfacing at the end

All three labs, underneath their surface topics (assembly, reliability, compliance), continue the
throughline this specialization has built since Day 1: **a claim about a system is only as good as
what actually checked it.** Day 1: a citation has to be checked against the real clause. Day 2: a
routing decision has to be checked by which tools actually fired, a memory fix has to be checked
by the specific recalled detail surfacing, an assist draft's quality has to be checked by a hook
outside the agent. Day 3 extends the same discipline to claims that were never really about the
agent's reasoning at all — a latency number, a failover, a compliance guarantee — and the fix is
identical in shape every time: name exactly what was measured, name exactly what wasn't, and never
let the two blur into one confident-sounding sentence.
