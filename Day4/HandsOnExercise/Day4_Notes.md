# Day 4 — Enterprise Integration, Security, Safety-Critical Actions

Core lesson: guardrails and permissions move from prompt text (mostly Day 1-3)
into deterministic code that gates BEFORE execution, always — the model's
judgment is never the only line of defense. AM labs introduce one new
deterministic primitive each in isolation; PM labs take a primitive from an
earlier day and add the production-grade concern (idempotency, full audit
trail, reusable compliance module).

Run from repo root: `.venv/Scripts/python.exe Day4_Labs/<lab>/solution.py`

---

## AM·H1 — Banking: Connect the Agent to a Ticketing System via MCP
`Day4_Labs/AM_H1_banking_mcp_ticketing/` · typed tools, create → resolve lifecycle

**Structure**
- `CREATE_TICKET_TOOL` — `priority` constrained via JSON schema `"enum": ["low","medium","high"]`; model physically cannot submit a 4th value.
- `TICKET_STORE` — plain dict keyed by generated `ticket_id` (`uuid4().hex[:6]`).
- `run_turn()` — identical shape to every earlier tool loop (Day1 H2/H3, Day2 PM·H1): `next()` tool_use check → execute → one followup call.
- Two-turn demo: create then resolve, same `ticket_id` recalled by the MODEL from its own conversation memory (not passed back explicitly by code).

**Test matrix**

| # | Turn | Input | Expected |
|---|---|---|---|
| 1 | 1 | "My transfer to my landlord failed and the money hasn't come back yet." | `create_ticket` called with sensible subject/description/priority; customer told their ticket number; `TICKET_STORE[id].status == "open"` |
| 2 | 2 | "Update — the money just came back on its own, you can close it out." | `resolve_ticket` called on the SAME ticket_id from turn 1; `TICKET_STORE[id].status == "resolved"`, `resolution_note` populated |

**Edge cases to cover**
- `resolve_ticket` called with a `ticket_id` that was never created — returns `{"error": "ticket not found"}`; confirm the agent relays that cleanly rather than claiming success.
- Reject a `create_ticket` call with an invalid `priority` (README stretch goal: the enum SHOULD prevent the model from ever sending one, so to actually test the error path you'd need to call `create_ticket` directly in Python, bypassing the schema) — see how the model responds when your code returns a validation error as the tool result instead of raising.
- Add `add_ticket_comment(ticket_id, comment)` (stretch goal) for a customer who adds detail BEFORE the ticket is resolved — not implemented in the reference solution.
- README's own discussion prompt: compare blast radius of the typed `priority` enum vs. a free-text priority string — where else in Day 1-3's labs would this same narrowing help? (Good group discussion, not a code exercise.)

---

## AM·H2 — Insurance: Guardrails + Prompt-Injection Defence, Then Attack It
`Day4_Labs/AM_H2_insurance_guardrails/` · layered input/output filters; retrieved content treated as untrusted

**Structure**
- `input_guardrail()`/`output_guardrail()` — both iterate a list of `re.search()` regex patterns against lowercased text. Crude on purpose — the lesson is architecture (2 independent filter points), not filter sophistication.
- `run_test_harness()` — computes true/false positives against labeled `test_cases.json`, prints per-case OK/MISS — literally an eval harness (previews Day 5).
- `protected_reply()` — input_guardrail gate BEFORE any API call (fail fast, no cost) → model call with untrusted-data framing in the system prompt → output_guardrail gate on the reply. 3 independent chances to catch an attack.

**Test matrix**

| # | Part | Input | Expected |
|---|---|---|---|
| 1 | 1 | All 5 adversarial cases in `test_cases.json` | ALL caught by `input_guardrail` |
| 2 | 1 | All 3 clean cases in `test_cases.json` | ZERO false positives |
| 3 | 2 | Each doc in `malicious_kb_docs.json` fed through `protected_reply("What's covered under this policy?", doc)` | Attack arrives via RETRIEVED content, not user text — `input_guardrail` is blind to it by design; either the system-prompt untrusted-data framing holds and the model ignores the injected instruction, OR `output_guardrail` catches a leak/persona-break in the reply |

**Edge cases to cover**
- README's own Part 2 setup — construct a NEW malicious doc that gets PAST current guardrails (stretch goal). This is the actual red-teaming loop; do it live, don't skip it.
- README's own discussion prompt: why do you need an output guardrail if the input looked clean? Answer directly demonstrated by test #3 above — the malicious content never touched `user_message` at all.
- A clean message that happens to CONTAIN one of the regex trigger phrases in an innocent context (e.g. a customer literally asking "can you ignore previous claims and just check this one") — false-positive stress test beyond the 3 provided clean cases.
- Log every flagged attempt (stretch goal) — seed of the security-incident audit trail PM·H2 builds fully.

---

## AM·H3 — Retail: Enforce Per-User Permissions on an Action
`Day4_Labs/AM_H3_retail_permissions/` · entitlement checks gate tool execution in CODE, not model judgment

**Structure**
- `check_permission()` — 3 sequential checks: user exists → owns the order → has the action-specific flag. Order matters: ownership fails FIRST even if the user would otherwise have the permission flag.
- `modify_order_gated()` — wraps the real `execute_modify_order()`; the permission check happens here, unconditionally, regardless of what the model decided.
- Tool schema (`priority`-style enum) can't encode this guardrail — permission depends on RUNTIME `user_id`, so it needs an explicit gate function, unlike AM·H1's ticketing.

**Test matrix**

| # | User | Request | Expected |
|---|---|---|---|
| 1 | `user_101` (owns ORD-500, `can_cancel=True`) | "Please cancel order ORD-500." | Allowed; `execute_modify_order` runs; order cancelled |
| 2 | `user_202` (does NOT own ORD-500) | "Please cancel order ORD-500." | Denied — reason: "user does not own this order"; agent relays a clear refusal; NO state changed |

**Edge cases to cover**
- A user who OWNS the order but lacks the specific action flag (e.g. owns it but `can_modify_quantity=False`, tries a quantity change) — confirm the reason string correctly says "user lacks permission for modify_quantity", distinct from the ownership failure message.
- Manager/role-override case (README stretch goal: a role that can act on ANY order regardless of `owns_orders`) — not implemented; adding it without duplicating the ownership check everywhere is the actual design challenge worth doing live.
- README's own discussion prompt: construct a prompt that tries to talk the model OUT of refusing (if refusal were the only defense) — then confirm `check_permission` still blocks it structurally regardless of what the model was persuaded to attempt. This is the single clearest demo in the whole course of "code gate vs. model judgment."
- `user_id` not present in `ENTITLEMENTS` at all — returns `(False, "unknown user")` — confirm this path is reachable and doesn't crash on a `KeyError`.
- Log every permission check (stretch goal) — seed of an access-control audit trail, formalized in PM·H1/PM·H2's audit patterns.

---

## PM·H1 — Banking: Idempotent, Audited Transactional Action via MCP
`Day4_Labs/PM_H1_banking_idempotent_action/` · idempotency keys + append-only audit logging around money-moving action

**Structure**
- `PROCESSED_KEYS` dict: `idempotency_key → stored result`. `process_refund()` checks this FIRST — key seen → return the IDENTICAL stored result without touching `REFUND_LEDGER` again.
- `audit_log()` — appends structured dict to module-level `AUDIT_LOG`, called on EVERY path inside `process_refund` (fresh AND replay), with a distinct action name `"process_refund_replay"` for the replay case — replay is invisible to the ledger/customer but NOT invisible to audit.
- Demo manually re-calls `process_refund()` directly with the SAME stored key, simulating a network-layer retry — not another model turn.

**Test matrix**

| # | Call | Expected |
|---|---|---|
| 1 | Model turn: "I was double-charged $45 for order #8821, please refund the duplicate charge." | `process_refund` called with a fresh model-generated `idempotency_key`; `REFUND_LEDGER` gets exactly 1 entry; `AUDIT_LOG` gets 1 entry (`process_refund`) |
| 2 | Direct retry: `process_refund(same transaction_id, same amount, SAME idempotency_key)` | `REFUND_LEDGER` STILL has exactly 1 entry (not double-processed); `AUDIT_LOG` now has 2 entries total — the 2nd is `process_refund_replay`, same result payload as the original |

**Edge cases to cover**
- Retry with the SAME `transaction_id`/`amount` but a DIFFERENT (freshly generated) `idempotency_key` — this is NOT deduplicated (by design — the key IS the dedup mechanism) — confirm this produces a SECOND ledger entry, and discuss why that's the exact risk the README's discussion prompt raises about letting the model generate a fresh key on every retry.
- Add the `max_amount` guardrail (stretch goal) — refuse any amount above a threshold in `process_refund` itself, regardless of what the model requests, and audit-log the refusal too. Not implemented; direct extension of AM·H3's code-level-gate pattern applied to a dollar amount instead of ownership.
- Replayable audit narrative (stretch goal) — a function that takes `AUDIT_LOG` and reconstructs a human-readable step-by-step account. Not implemented here; PM·H2 builds exactly this (`replay_audit_trail`) for a different pipeline — worth pointing out the two are the same pattern.
- Two DIFFERENT customers' refunds interleaved in the same run — confirm `PROCESSED_KEYS` (global, not scoped per customer) never cross-matches one customer's idempotency key against another's request.

---

## PM·H2 — Insurance: Defence-in-Depth Guardrail Stack + Replayable Audit Trail
`Day4_Labs/PM_H2_insurance_defense_in_depth/` · composes AM·H2's filters + 2 new layers, everything logged

**Structure**
- `log_step()` — appends `{timestamp, step, detail}` to `AUDIT_TRAIL` for literally every stage: input_guardrail result, model_call params, flag_for_review usage, output_guardrail result, final outcome.
- New vs. AM·H2: `FLAG_FOR_REVIEW_TOOL` gives the MODEL an explicit tool to bail via ("call this instead of answering if uncertain") — a 4th independent defense line, model-invoked rather than code-invoked, sitting between layers 2 and 3.
- `replay_audit_trail()` — pure formatter looping `AUDIT_TRAIL`, proving the log alone is sufficient to reconstruct what happened without re-running anything.

**Test matrix**

| # | Run | Input | Expected `AUDIT_TRAIL` |
|---|---|---|---|
| 1 | Clean | "Does my policy cover towing?" + clean roadside-assistance doc | `input_guardrail(flagged=False)` → `model_call` → `output_guardrail(flagged=False)` → `outcome: answered` |
| 2 | Adversarial | "What's covered under this policy?" + `MALICIOUS_DOCS[1]` | Either `flag_for_review` fires (model catches the injected instruction itself) OR `output_guardrail` catches a leak — trail makes clear WHICH layer actually stopped it |

**Edge cases to cover**
- README's own "what's missing" discussion prompt: if a security incident happened 3 weeks ago, does `AUDIT_TRAIL` contain enough for someone to reconstruct EXACTLY what the agent saw, decided, and said — WITHOUT re-running anything? Walk through a saved trail and check for gaps (e.g. is the exact retrieved doc content logged, or just its id?).
- Export `AUDIT_TRAIL` to JSON keyed by conversation id (stretch goal) — not implemented; the shape a real SIEM/logging pipeline would need.
- Severity field on flagged entries (stretch goal) — not implemented; without it, `replay_audit_trail` treats a routine pass and a caught attack with equal visual weight.
- A malicious doc that gets PAST all 4 layers (construct one deliberately) — confirms the "defense in depth, not defense in certainty" framing; the point isn't that this stack is unbreakable.

---

## PM·H3 — Retail: Assemble a CX Compliance Pack
`Day4_Labs/PM_H3_retail_compliance_pack/` · reusable consent/disclosure/retention/deletion module, NO API key needed

**Structure**
- `CompliancePack.records` — `{customer_id: [record, ...]}`, ALL record types (disclosure, consent, interaction_log) in ONE flat list per customer, distinguished by a `"type"` key — simpler than Day2 PM·H2's two-tier split because retention/deletion need to operate uniformly across all types.
- `check_consent()` — filters by type+purpose, `max(..., key=timestamp)` — most-recent-wins, keeping FULL history rather than overwriting in place.
- `apply_retention_policy()` — single unconditional sweep by cutoff date across ALL customers; deletes the customer key entirely if nothing survives.
- `handle_deletion_request()` — single `dict.pop(customer_id, None)` — cheap because of the flat-record-list design.

**Test matrix**

| # | Call | Expected |
|---|---|---|
| 1 | `disclose(cid)` | Returns disclosure string; 1 record logged |
| 2 | `capture_consent(cid, "data_processing", True)` then `check_consent(cid, "data_processing")` | Returns `True` |
| 3 | `capture_consent(cid, "marketing_contact", False)` then `check_consent(cid, "marketing_contact")` | Returns `False` |
| 4 | `capture_consent(cid, "marketing_contact", True)` (2nd record, same purpose) then re-check | Returns `True` — most recent record wins, old one still in history |
| 5 | Insert a record backdated 400 days, then `apply_retention_policy(retention_days=365)` | Records before = 5, after = 4 (the 400-day-old one purged, everything else survives) |
| 6 | `handle_deletion_request(cid)` | Returns confirmation string; `pack.records.get(cid)` is `None` afterward |

**Edge cases to cover**
- README's own discussion prompt: what's the risk of treating consent as a single overwritten boolean instead of a history? Directly demoed by test #4 above — try DELETING the history-keeping (`max` over all records) and replacing it with in-place overwrite, then ask what an auditor loses.
- `apply_retention_policy` called when a customer's records are ALL older than the cutoff — confirm the customer key is deleted entirely (`del self.records[customer_id]`), not left as an empty list.
- `check_consent` for a `purpose` that was never captured at all — returns `False` (the "no consent on file" default), confirm that's the intended fail-closed behavior, not an exception.
- `export_for_subject_access_request` (stretch goal, the "what do you have on me" GDPR/DPDP request, distinct from deletion) — not implemented.
- Per-record-type retention periods (stretch goal — e.g. consent records retained longer than routine logs) — not implemented; current policy is uniform across all types.
