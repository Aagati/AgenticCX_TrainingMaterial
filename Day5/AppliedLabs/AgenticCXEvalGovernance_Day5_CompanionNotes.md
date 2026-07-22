# Day 5 — Post-Lunch Applied Lab: Companion Notes

**Notebook:** `AgenticCXEvalGovernance_Day5AL.ipynb` · **Lanes:** Banking (H1) · Insurance (H2) · Retail / Team (H3) · **Duration:** 4h

Same convention as Days 1–4's companion notes: the notebook carries the walkthrough, this document
goes one layer deeper — the reasoning, misconceptions, and production context behind each lab.

---

## Why this day matters, and why it's the least "new capability" day of the week

Every prior day added a capability: Day 1 a resolution agent, Day 2 multi-agent memory, Day 3 voice,
Day 4 safe actions. Day 5 adds none. It is deliberately the day that turns around and *measures*
everything already built. That reframing is worth naming out loud at the start, because it changes
what "success" looks like: there is no new demo that impresses by working. The impressive thing today
is a number you can defend, a gate that says no, and a governance artifact an auditor could read
without ever trusting the agent that produced it.

The verification ratio is the clearest signal of what kind of day this is. Day 3 was mostly Tier B/C
because voice needs hardware and provider accounts. Day 4 flipped to mostly Tier A because the real
guarantees (idempotency, injection defence, permissions) are deterministic server-side logic. Day 5
goes almost all the way: **exactly one Tier B cell**, and it exists only to prove a live-generated
trajectory feeds the same deterministic graders everything else uses. That is not an accident of the
sandbox — it is the thesis. Evaluation is the one discipline that *should* be nearly deterministic,
because its entire job is to be the fixed point you measure a probabilistic system against. If your
eval suite is itself probabilistic, you have not built an eval suite; you have built a second thing
that also needs evaluating.

**What this changes about how the session should run:** resist any instinct to treat the single live
cell as the "real" part and the Tier A graders as setup for it. It is the reverse, more strongly than
any prior day. The graders are the deliverable. The live model turn is one input to them, included so
nobody leaves thinking evaluation requires live infrastructure — it doesn't, and the notebook proves
it doesn't by grading recorded goldens for nine of ten steps.

---

## Setup and the "reused foundations" block

Day 5 introduces no new install beyond what Days 1–4 needed — `claude-agent-sdk` and Day 3's `jiwer`.
The one structural choice worth explaining is the three-cell **reused foundations** block near the
top. Days 3 and 4 re-declared earlier artifacts inline because these notebooks are self-contained and
not cross-imported over `sys.path`. Day 5 reuses *more* earlier artifacts than any other day — the KB
and retrieval, the idempotent action tool, the audit substrate, the safety graders, the permission
gate, the instrumentation logs, the WER gate — so rather than scatter them, they're gathered into
three grouped cells (resolution+instrumentation, audit+safety+permission, QA+WER). Everything after
them is genuinely new eval/governance code. Worth saying plainly to trainees: if a name looks
familiar, it is; the foundations block is exactly the Day 1–4 code, pasted verbatim, so the ten steps
can be about evaluation and nothing else.

One small robustness note: the foundations cell writes `compliance_policy.json` if it's missing,
self-healing the Day 4 dependency so a trainee who only has the `day5/` folder can still run the
governance step. The file that ships alongside the notebook is identical to Day 4's.

---

## Lab H2 — Insurance: the eval gate (Steps 1–4)

H2 is where "end-to-end hardening" and "eval-gated rollout" actually land, so it's built up across
four steps before being named as the gate.

### The golden set is only as honest as its predictor (Step 1)

The single most common way a golden-based eval lies is that the "predictor" secretly reads the
answer key. The notebook is deliberate about this: `predict_resolution` decides resolved-vs-escalated
*from the retrieval score* (`RESOLUTION_SCORE_MIN`), never from the golden's `expected_outcome`
label. The knee-surgery query scores far below the insurance clauses and correctly predicts
"escalated" on its own. Worth demonstrating live by editing a golden's expected label to something
wrong and watching the eval correctly fail — proof the predictor is genuinely independent of the key.
This is the same discipline as Day 1's citation check (present *and* correct) and Day 2's
"check both specialists were actually called," one level up: an eval that can't fail on bad input is
testing nothing.

### Trajectory eval catches what a final-answer check can't (Step 2)

A resolution eval grades the destination; a trajectory eval grades the route. This matters because
Day 1 already surfaced the exact failure it catches: an agent that mints a *new* idempotency key on
the confirm turn produces a correct-looking preview and a correct-looking confirmation while
double-filing under the hood. `score_trajectory` checks order and key-reuse statically, but the
load-bearing move is `replay_claim_calls`, which drives the recorded calls through Day 1's **real**
`file_claim.handler` and asserts the sequence files exactly one claim and that replaying it is a
genuine no-op. Grading against the actual tool logic, not a description of it, is what makes this a
test rather than a restatement of the trajectory.

### The judge is advisory; the deterministic checks are the assertion (Step 3)

This is the step most likely to be misremembered, so it's worth being precise. An LLM-as-judge is the
industry-standard tool for scoring fuzzy quality — but it is itself non-deterministic, which means
its verdict is a *third* probabilistic output that would, taken as ground truth, need its own
evaluation. The notebook's `rubric_judge` is a deterministic stand-in with the same rubric shape
(cited / grounded / confident), and the markdown is explicit that in production this one function
body becomes a model call while everything consuming its `{"score": ...}` output stays identical.
The teaching line: **keep the narrow-but-reliable deterministic checks as your `assert`; treat the
flexible-but-fuzzy judge as an advisory signal.** Day 3's `wer_gate` is reused verbatim here as the
voice-channel resolution grader precisely to make that point concrete — the same "grade a
probabilistic system with a plain assertion" move, applied one more time. The single Tier B cell sits
right after this step for a reason: it shows the judge and the trajectory scorer both consuming a
live-generated trajectory, so trainees see the deterministic graders eating real model output, not
just canned goldens.

### The gate combines quality and safety, but safety is absolute (Step 4)

H2's gate is a single dict with a `passed` boolean, and the asymmetry inside it is the lesson: a
resolution pass rate is a *threshold* (0.9 is fine, 0.95 is better), but the two safety invariants —
0 canary leaks, 0 unauthorized actions — are *absolutes*. A resolution score of 0.95 ships; a single
canary leak does not, no matter how good every other number is. Both safety checks reuse Day 4 code
unchanged: `scan_output_for_leak` over a batch of outputs, and `make_can_use_tool` replayed over a
batch of permission attempts with a count of allows that shouldn't have happened. Worth stressing that
"0 unauthorized" is measured by actually running the gate over wrong-owner attempts and confirming
none returned `Allow` — not by asserting the gate exists.

---

## Lab H1 — Banking: the governance pack (Step 7)

### An agent card is only useful if it can't drift from the code

The failure mode a governance pack exists to prevent is a beautifully written document that describes
an agent that no longer exists. The notebook builds the agent card *from* the tool allowlist and
`compliance_policy.json`'s role scopes, not from hand-authored prose — so the "permissions" section
is literally the enforced policy, and the "tools" section is literally the allowlist, and neither can
say something the running system doesn't do. This is the policy-as-config payoff from Day 4 pointed at
documentation instead of enforcement: the same JSON that *enforces* the refund limit also *describes*
it, so they can't disagree.

### Disclosure is Day 3's pattern, generalised past voice

The disclosure statement reuses Day 3's `CompliantCallFlow` consent-disclosure text pattern,
generalised from a phone call to any channel: an AI-disclosure line, the policy's own consent text,
and the promise of a replayable audit trail. The audit trail itself is Day 4's `replay_events` over
the entities the agent touched. Bundled, the three pieces (card, trail, disclosure) plus the eval
summary are a single `dict` — the point being that a reviewer, or an auditor months later, reads the
artifact and never has to trust or re-run the subject. That "verify from outside" principle is the
through-line from Day 2's QA hook and Day 3's replay onward.

---

## ROI, the release gate, and the capstone (Steps 8–10)

### Containment and deflection are not the same number (Step 8)

The most important thing in the ROI dashboard is that `containment_rate` (resolved / total) and
`deflection_rate` ((total − escalated) / total) come out *different* — 0.7 versus 0.8 on the sample
batch — because a `failed` conversation deflected a human without resolving anything. Conflating them
is the exact deflection-vs-resolution confusion Day 1 spent its first lab warning about, now showing
up as a metrics bug instead of a design bug. If a dashboard reports the two as identical, someone
computed deflection as resolved/total and quietly erased the distinction that matters most.

### The release gate has to be able to say no (Step 9)

Day 4 gated a single tool call with `PreToolUse`; Step 9 gates a whole release with the same
deterministic discipline. `can_we_ship` returns not just a boolean but the *reasons*, and the notebook
proves the gate can block by injecting a single canary leak and confirming it flips to `ship: False`
with a named reason. A gate that only ever passes in the demo is indistinguishable from no gate; the
injected-leak test is what proves it's real, the same way Day 4's H3 proved the permission callback
was actually consulted rather than silently shadowed.

### The capstone brief is filled from results, not aspirations (Step 10)

H3's brief is the one page a stakeholder signs, and every metric in it comes from `metrics_snapshot`,
`roi`, and `ship_decision` — the real outputs of Steps 1–9. Filling it from live results rather than
intentions is the capstone-scale version of grounding: a brief whose metrics section is blank or
invented is the capstone equivalent of an uncited answer. The template is reusable; the worked
example is what proves the template survives contact with real numbers.

---

## Continuity, named out loud

Day 5 reuses more prior-day material than any other day — it is, by design, the day that grades the
week — so it's worth enumerating exactly what came from where (same discipline Days 2–4 used):

- **Day 1:** `policy_chunks`/`score`/`search` (the golden resolution eval in Step 1 grades this real
  retrieval); the idempotent `file_claim` + `pending_claims`/`filed_claims` (Step 2 replays
  trajectories through it); `conversation_log`/`log_outcome` (Lab 3's instrumentation is the raw
  material for Step 5's online QA and Step 8's ROI — the notebook Day 1 explicitly said "Day 5's
  evaluation framework consumes later").
- **Day 2:** `claims_db` (the Insurance claim data); `return_chunks`/`retail_search` (Retail lane);
  `qa_log`/`log_assist_review` (the human-review QA-hook pattern that Step 5's online QA generalises);
  and the `_run_specialist` helper used by the single Tier B cell to capture a live answer as a string.
- **Day 3:** `wer_gate` (reused verbatim as Step 3's voice-channel resolution-quality grader — the
  canonical "grade a probabilistic system with a plain assertion" pattern); the `CompliantCallFlow`
  consent-disclosure text pattern (generalised into Step 7's disclosure statement).
- **Day 4:** `audit_log`/`log_audit`/`replay_events` (the generalized-to-any-`entity_id` version,
  which Step 6's observability stream generalises once more, to metrics keyed by `run_id`);
  `scan_output_for_leak`/`detect_injection`/`_injection_re` (Step 3's grounding check and Step 4's
  canary invariant); `make_can_use_tool` (Step 4's unauthorized-action invariant);
  `compliance_policy.json` (Step 7's agent-card permissions and consent text).

Nothing in the ten steps starts from scratch; every step is a grader or a report wrapped around code
an earlier day already proved correct. That is the point of putting evaluation last: you can only
grade what already exists.

---

## Closing

The thread underneath all three labs, stated the way Day 4's closing was ("an action is safe only if
something outside the agent's own good intentions can prove it"): **a CX agent is trustworthy only if
it's measured outside its own success claims.** H2 measured it for quality and safety — goldens the
agent didn't write, invariants that are Python-level facts. H1 measured it for governance — a pack
assembled from config and logs, readable by an auditor who never trusts the subject. H3 measured it
for the business case — a brief whose every number is downstream of instrumentation, not marketing.
The single finding worth returning to if the session has time for only one: the notebook is nine-parts
Tier A and one-part Tier B *on purpose*, because an evaluation suite that is itself probabilistic
isn't an evaluation suite — it's a second system that also needs one. The whole week has insisted on
finding the one thing about a probabilistic system you can check with a plain assertion; Day 5 is that
insistence turned into the deliverable.
