# Day 4 — Post-Lunch Applied Lab: Companion Notes

**Notebook:** `AgenticCXSafeActions_Day4AL.ipynb` · **Lanes:** Banking (H1) · Insurance (H2) · Retail (H3) · **Duration:** 4h

Same convention as Days 1–3's companion notes: the notebook carries the walkthrough, this
document goes one layer deeper — the reasoning, misconceptions, and production context behind
each lab.

---

## Why this is the most Tier-A day of the week, and why that mattered going in

Day 3 forced a three-tier verification split because voice needs a network, a microphone, and a
paid provider account, none of which exist in this sandbox. Day 4's ship line — "safely takes a
real system action, with guardrails and an audit trail" — sounds like it should carry the same
constraint (a *real* system action implies a real external system). It doesn't, and that's worth
naming out loud in the session: everything Day 4 actually needs to teach — idempotency,
injection defence, permission enforcement, consent, retention — is **deterministic server-side
logic**, testable by calling a function or a callback directly, with no model and no network.
The one place a real external account would matter (an actual Zendesk/ServiceNow behind the
ticketing lab) was deliberately kept out: `ticketing_mcp_server.py` is a real, separate OS
process speaking the real MCP protocol, with a mocked backend behind it. The protocol boundary —
the part this curriculum can actually teach without a trainee's own SaaS credentials — is real;
the account behind it isn't. That's the same "mocked-but-real-protocol" move Day 3 made for
telephony, just with a much higher Tier-A ratio riding on it.

**What this changes about how the session should run:** resist the temptation to treat the live
(Tier B) cells as the "real" verification and the offline (Tier A) cells as a formality before
them. It's the reverse this time. The offline cells are where the actual guarantees live —
idempotency held under a direct retry call, the injection detector flagged the exact malicious
string, the permission gate returned `Deny` for the wrong-owner call — and they hold regardless
of what any one live model run happens to do. The live cells exist to prove the wiring is real,
not to be the thing trainees trust.

---

## Setup

No new auth gotcha this time — Day 4 stays entirely on `claude_agent_sdk`, so whatever
authentication got Day 1–3 running (`claude login` or `ANTHROPIC_API_KEY`) covers this notebook
too. The one environmental requirement worth calling out before anyone hits it: every cell
assumes the notebook's working directory is `day4/`, because `ticketing_mcp_server.py` is
launched by a **relative** path (`args=["ticketing_mcp_server.py"]`). A trainee running the
notebook from the project root instead of `day4/` will get a real, if slightly cryptic, process-
launch failure — worth a one-line warning before Step 1.

---

## Lab H1 — Banking: safe, audited action (idempotent + audited via MCP)

### The one new mechanism of the day, and why it was worth the risk

Days 1–3 all used `create_sdk_mcp_server` — an in-process tool registered on an object living in
the same Python process as the agent. `ticketing_mcp_server.py` is a **genuinely separate OS
process**, launched over stdio, speaking the real MCP protocol. This is the curriculum's only
natural home for that distinction: contents.md names "MCP integration" as a distinct Day-4 topic,
and if H1 had reused the in-process pattern a fourth time, that topic would have taught nothing
new. It was flagged as the highest live-failure risk on Windows going in (subprocess launch,
venv python path, working directory) — worth saying plainly that **it worked on the first real
attempt**, verified three separate ways before it ever reached the notebook: the `mcp` package's
own stdio client talking to the server directly (no `claude_agent_sdk` involved at all), then
`claude_agent_sdk`'s `mcp_servers={"type":"stdio",...}` config driving a real two-turn
conversation through it. No fallback to the in-process pattern was needed, but if it had failed
live in front of a class, that would have been the recovery path — worth keeping in your back
pocket even though this notebook didn't need it.

### Idempotency lives in the wrong place if it lives in the agent

Day 1's `file_claim` idempotency (`pending_claims`/`filed_claims` dicts) lived in the same
process as the agent driving it — which works for a teaching demo, but doesn't match where
idempotency actually has to live in production: a network retry re-invokes the *external
system*, not the agent process that happened to be running when the first attempt was made.
`ticketing_mcp_server.py` moves that logic to where a retry actually lands. The teaching point
worth drawing out live: `create_ticket`'s idempotency alone isn't the interesting part —
`resolve_ticket` treating "resolved" as a **terminal state**, where the same resolution replayed
is a safe no-op but a *different* resolution is a refused conflict, is the part that actually
prevents a real bug (two support agents' retries silently overwriting each other's outcome).

### A subtlety worth walking through slowly: two processes, two ticket stores

Step 1 imports `ticketing_mcp_server` directly to unit-test its idempotency logic — fast, no
subprocess, no model. Step 2 then launches that *same file* as a **separate subprocess** for the
live agent conversation. These are two different Python processes with two independent `tickets`
dicts that happen to share a class definition but share zero memory. A ticket created in Step 1
does not exist from the subprocess's point of view, and vice versa. This tripped up an early
draft of this notebook — a cell that printed the directly-imported module's `tickets` dict right
after the live conversation, which showed Step 1's leftover state and made it *look* like the
live conversation's ticket had vanished. The fix was to stop peeking at the wrong process's
memory and instead print the raw `ToolResultBlock` content the subprocess actually returned over
the stdio pipe — which is also a better demo, since it's literal proof the round trip crossed a
real process boundary. Worth walking trainees through this distinction explicitly; it is the
single most likely place someone writes a "the tool must be broken" bug report that's actually a
correct two-process design.

**The same mistake resurfaced one cell later, in Step 3's replay** — worth naming honestly rather
than pretending the first fix made the whole notebook immune to it. An earlier draft of the Step
3 cell peeked at `ticketing.tickets` (the directly-imported Step 1 module) to find "whichever
ticket turn 1 minted," which — for the exact reason above — can only ever resolve to Step 1's own
offline ticket; the live conversation's ticket was never reachable from there. Since the
subprocess's `tickets`/`audit_log` dicts don't survive past the `async with` block in Step 2
closing, replaying the *live* ticket has exactly one valid window: while that session is still
open. The fix adds a fourth turn to Step 2's conversation — "replay this ticket's full audit
history" — so the agent calls `replay_ticket` itself, from inside the same live session, and
Step 3 is left doing only what it can honestly do from outside that session: replay the Step 1
offline ticket. The generalizable lesson is the same one H3's `CanUseToolShadowedWarning` teaches
later in this same notebook: a control (or in this case, a demo) that looks right in isolation
needs to be checked against *what process actually holds the state it's reading*, not just
whether the code runs without raising.

---

## Lab H2 — Insurance: auditable agent — defence-in-depth + prompt-injection

### The attack had to be built to reliably win retrieval, on purpose

`score()`'s keyword-overlap retrieval is deterministic, not probabilistic — so unlike whether
the *model* takes the bait, whether the poisoned chunk gets *retrieved* is fully controllable.
The malicious `POL-9.9` chunk's wording was tuned (it shares "policy", "claim", and "special"
with the query) specifically so it reliably outranks the four legitimate clauses, verified with
an assertion right after `search_poisoned()` is defined, before any agent ever sees it. That
assertion is what makes the rest of the lab trustworthy — if the poison hadn't actually reached
top-3, everything downstream would be testing nothing.

### An honest surprise worth naming in the room: the undefended run resisted the injection too

Going in, Step 4's undefended live run was written expecting to *observe*, not assert, whether
the model took the bait — genuinely uncertain either way, hence the "illustrative, not
guaranteed" framing. In the runs behind this notebook, the model recognized `POL-9.9` as an
injection attempt on its own and refused to act on it, without any of Steps 5–9's defences
in place. That's a real, useful thing to say to a class: modern models have real, if
inconsistent, resistance to naive injections baked into their own training — but "the model
usually catches it" is not a security boundary anyone should ship on. That's precisely why Step
9's decisive layer is a **Python-level guarantee** (the malicious text is redacted before the
model's context is even built) rather than "and then we trust the model to notice" — the
defence has to hold even against a future model, or a differently-phrased attack, that doesn't
happen to resist it.

### Why the canary token matters more than it looks

`PWNED-1234` is not decoration — it's what turns "did the injection work" from a subjective
read of the model's prose into a single deterministic string search
(`scan_output_for_leak`). This is the same move as Day 3's WER gate and VAD benchmark: find the
one thing about a probabilistic system that can be checked with a plain assertion, and build the
lesson's verification around that, instead of trying to grade free-text output by eye.

### Four layers, and which one is actually load-bearing

Worth being explicit with trainees about the hierarchy, not just listing four checkmarks:
capability reduction (Layer 2) is the strongest guarantee, because it removes the *possibility*
of the bad outcome structurally — a coverage-only agent literally cannot call `file_claim`,
regardless of what any layer above it does or doesn't catch. Input filtering (Layer 1) is next —
deterministic, runs in Python, doesn't depend on the model reading correctly. The `PreToolUse`
hook (Layer 3) and output scan (Layer 4) are real, useful, and *also* deterministically testable
— but they're catching what got past the earlier layers, not preventing it from being attempted.
Defence-in-depth means having all four, not treating any single one as sufficient on its own.

---

## Lab H3 — Retail: per-user permissions + compliance pack

### The gotcha that would have shipped silently: `allowed_tools` shadowing `can_use_tool`

This is the most important bug this notebook found, and it's worth spending real class time on
it rather than rushing past. The first draft of Step 13 put `cancel_order` and `apply_refund` in
`allowed_tools` right alongside `kb_search` — which felt natural, since every prior day's tools
lived there. Running it live produced a `CanUseToolShadowedWarning`: an `allowed_tools` entry
that whitelists a tool outright **auto-approves every call to it before `can_use_tool` is ever
consulted**. The permission gate built and unit-tested in Step 12 was, in that draft, completely
disconnected from the live agent — and every one of Step 12's direct-call tests still passed,
because they call `check_permission()` directly, bypassing the whole question of whether the SDK
would ever actually invoke it in a real conversation. **A callback that's never invoked passes
every test that calls it directly.** That sentence is the actual lesson, and it generalises past
this one API: whenever a security control has an "and here's how you'd unit test it" story, ask
the second question too — is anything in this configuration capable of making the runtime skip
calling it at all? The fix was small (drop the whole-tool entries, leave `cancel_order`/
`apply_refund` off `allowed_tools` so calls fall through to the callback) but the *finding*
process — a live run producing a warning that a static review of the code would not have caught
— is the actual teaching moment. Worth reproducing live in class if time allows: run it with the
tools whitelisted, show the gate never fires; remove them, show it does.

### Binding identity outside the model's reach

`make_can_use_tool(acting_user_id, policy)` closes over `acting_user_id` as a value the
*surrounding application* supplies — the same place a real session's authenticated identity
would come from (a login token, a session cookie), never as an argument inside `tool_input`. This
is worth contrasting explicitly with a tempting-looking alternative: passing `user_id` as a tool
argument and trusting the model to fill it in correctly. That version is trivially bypassable —
any customer can simply ask the model to act "as cust-002," and the model has no way to verify
that claim because it has no independent channel to the truth. Binding identity outside the
model's control is what turns this from a suggestion into an actual authorization boundary — the
same category of lesson as H2's Layer 2 capability reduction: the guarantee that holds is the one
the model cannot talk its way around.

### BOLA, not just RBAC

The permission checks in Step 12 are deliberately shaped to distinguish two things a naive
role-only gate would conflate: "is a customer allowed to cancel orders" (role) versus "is *this*
customer's order actually theirs" (ownership). Broken object-level authorization — correct role,
wrong target object — is the OWASP API security list's #1 risk for a reason: it's the failure
mode a superficial "does this role have this permission" check misses entirely. `cust-001`
attempting to cancel `ORD-501` (which belongs to `cust-002`) is the test that actually matters
here, more than any role-based check alone would have been.

### Consent/disclosure as a direct generalisation, retention as the new piece

`ActionConsentGate` is Day 3's `CompliantCallFlow` with the state names generalised from a phone
call to any action-taking session — same structural guarantee (authorization can only become
`True` via `on_consent_response(granted=True)`, no other code path sets it), same three
scenarios, same replayability. That reuse is deliberate and worth naming to trainees as a
pattern, not just an implementation shortcut: a well-designed compliance gate for one channel
often ports to another with nothing but renaming. Retention (`purge_expired`) is the one
genuinely new piece this week — records that don't just get created and audited, but expire.

### Policy-as-config as the literal payoff of a Day-1 forward reference

Day 1's companion notes named persona-as-config as "Day 4 territory (policy-as-config)" — Step 16
is that promise being kept. The same `check_permission`/`purge_expired` code, pointed at
`compliance_policy.json`'s `strict` vs `lax` profile, enforces different behaviour with zero code
change. Worth having trainees actually edit a number in the JSON file live and re-run the cell —
seeing the enforced limit change without touching a single line of Python is a more convincing
demonstration than reading the assertion.

---

## Continuity, named out loud

Every lab extends artifacts from earlier in the week rather than starting fresh, and it's worth
saying so explicitly in the session (same discipline Days 2–3 used):

- **Shared audit substrate:** `audit_log`/`log_audit`/`replay_events` (H2, H3) generalise Day 3's
  `audit_log`/`log_audit`/`replay_final_state` to any `entity_id`. H1's own audit trail
  deliberately did **not** use this — it lives inside `ticketing_mcp_server.py` instead, because
  that's the system that actually performed the action, a stronger guarantee than anything living
  in the notebook's own process.
- **H1** is the literal realisation of Day 1's stubbed `escalate_to_human` comment — "In
  production: push to your helpdesk/CRM queue via MCP" — and reuses Day 1's idempotency shape.
- **H2** reuses Day 1's `policy_chunks`/`search`/`file_claim` verbatim, poisons the KB with one
  added chunk, and reuses Day 1's `BUILTIN_LOCKDOWN` capability-reduction move one level up
  (a coverage-only agent with zero action tools, the same shape as Day 2's supervisor with zero
  domain tools).
- **H3** reuses Day 2's Retail `return_chunks`/`retail_search` verbatim, and its consent gate
  generalises Day 3's `CompliantCallFlow` almost unchanged.

---

## Closing

The thread underneath all three labs: **an action is only as safe as something outside the
agent's own good intentions can prove, before, during, and after the fact** — H1 proves it
*before* (idempotency, structurally), H2 proves it *during* (redaction that doesn't depend on the
model's judgement), H3 proves it *after* (a permission check the runtime cannot silently skip,
once the shadowing bug was found and fixed). The `CanUseToolShadowedWarning` finding is the one
worth returning to if the session only has time to dwell on one bug: it's the clearest example
this week of a control that looked correct in isolation and was provably disconnected from the
system it was meant to protect — findable only by running it live, exactly the discipline this
whole curriculum has insisted on since Day 1.
