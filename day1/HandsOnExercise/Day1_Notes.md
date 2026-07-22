# Day 1 — Foundations: Single-Turn → Tool-Call → Multi-Tool Loop

Progression across the day: read-only Q&A (no tools) → irreversible action with a
confirmation gate → multi-tool escalation loop. Each lab's guardrail model gets
stricter because the tool's blast radius gets bigger.

Run each lab from `Day1_Labs/` (root) using the shared root venv:
```
.venv/Scripts/python.exe Day1_Labs/H1_insurance_chat_agent/solution.py
```

---

## H1 — Insurance: Chat Agent with Citations
`Day1_Labs/H1_insurance_chat_agent/` · retrieve → ground → answer

**Structure**
- `retrieve(question, top_k=2)` — keyword-overlap scoring (tokenize, set-intersection vs each KB doc, sort desc, keep only score > 0). No embeddings.
- `build_grounded_prompt()` — stuffs only the retrieved docs into the user turn; hard-instructs "answer ONLY from context," cite `[POL-xxx]`, refuse if nothing matches.
- `answer_question()` — single `messages.create` call, no `tools` param — plain generation, one shot.
- Safety mechanism is the retrieval gate itself: empty retrieval → forced "I don't know" instruction, not model self-restraint.

**Test matrix**

| # | Input question | Expected output |
|---|---|---|
| 1 | "How many days do I have to file a two-wheeler claim after an accident?" | Cites `[POL-001]`, states 48-hour intimation window |
| 2 | "If I make one claim this year, what happens to my No Claim Bonus?" | Cites `[POL-002]`, NCB resets to 0% at next renewal |
| 3 | "Is my pet's vet bill covered under my health policy?" | No doc matches "pet" → retrieval returns `[]` → exact reply "I don't have this information in the policy documents I can access." |

**Edge cases to cover**
- Question spanning two clauses at once (e.g. claim filing + NCB together) — does it cite both ids or just one?
- Feed a retrieved-but-wrong clause on purpose (unrelated doc) — does the model still cite confidently on a plausible-sounding but wrong answer? (this is the README's own discussion prompt — worth actually running)
- Question with zero token overlap but a real answer exists in KB under different wording — tests the retrieval method's recall limit, not the model.
- Very short question ("covered?") — extraction/tokenizer edge case, most stopwords stripped, may retrieve nothing.

---

## H2 — Banking: Action Tool with Confirmation Step
`Day1_Labs/H2_banking_action_tool/` · understand → confirm → act

**Structure**
- `BLOCK_CARD_TOOL` — typed schema, `card_last4` + `reason` both required strings.
- `SYSTEM_PROMPT` carries the guardrail in text: "never call block_card without prior explicit confirmation" — no code-level gate, pure prompt engineering (contrast Day 4's `check_permission`, which gates in code).
- `run_turn()` — checks for a `tool_use` block via `next()`. None found → plain text turn (this is how the first message gets a clarifying question instead of instant action). Found → execute stub, append `tool_result`, ONE follow-up call for the natural-language wrap-up.
- `__main__` manually drives exactly 2 turns to simulate ask → confirm → act.

**Test matrix**

| # | Turn | Input | Expected output |
|---|---|---|---|
| 1 | 1 | "Hi, my card was stolen, please block it right now." | Agent asks which card / for explicit confirmation — does **not** call `block_card` yet |
| 2 | 2 | "Yes, it's the one ending 4471, please block it." | `[SYSTEM] Blocking card ending 4471...` printed; agent replies with confirmation number `BLK-88213` + replacement-card timeline (5-7 business days) |

**Edge cases to cover**
- Remove the confirmation guard from the system prompt (README's own suggested experiment) — how often does the model call `block_card` on turn 1 anyway? Quantify it, don't just eyeball once.
- Customer states card number in the SAME message as the stolen-card report ("card ending 4471 was stolen, block it now") — does the agent still insert a confirmation question, or skip straight to calling the tool since ambiguity is already resolved?
- Customer never confirms, sends an unrelated message instead — does `run_turn` correctly stay in the no-tool-call branch indefinitely?
- Multiple cards on file (stretch goal: add `list_cards`) — confirm disambiguation instead of guessing a card number.

---

## H3 — Retail: Escalation with Full Context Handoff
`Day1_Labs/H3_retail_escalation/` · confirm → escalate with context (capstone)

**Structure**
- `TOOLS` list + `TOOL_FUNCS` dispatch dict (name → callable) — more scalable than H2's single `next()` check since this loop can call more than one tool across turns.
- `run_conversation()` — `for _ in range(max_iterations)` bounded loop. Collects ALL `tool_use` blocks per pass (plural — model may call `get_order_status` then later `escalate_to_human`). No blocks → return text, done. Blocks found → execute each, batch results into one `tool_result` list, loop again. Falls through to `"[max iterations reached]"` if it never converges — a safety valve H2 didn't have.
- `REFUND_AUTHORITY_LIMIT = 1500` — guardrail lives only in `SYSTEM_PROMPT` text (not enforced in code — contrast Day 4 PM·H1's `process_refund`, which enforces limits in code).
- `ESCALATE_TOOL` schema forces complete context via `required` fields — that part IS structurally enforced.

**Test matrix**

| # | Input | Expected flow |
|---|---|---|
| 1 | "My order ORD-4021 was never delivered but I was charged 2400 rupees... I want a full refund right now." | 1) `get_order_status("ORD-4021")` → `delivered=False, amount=2400`. 2) 2400 > 1500 limit → `escalate_to_human` called with real summary/sentiment/order_id/requested_action/full transcript (no "TBD" placeholders). 3) Ticket `TCK-77190` printed. 4) Final text reassures customer a specialist has full context. |

**Edge cases to cover**
- Refund request under the 1500 limit — should NOT escalate on amount grounds; confirm the agent handles it itself or asks a clarifying question instead.
- Customer explicitly says "let me talk to a supervisor" with no refund amount involved — second escalation trigger, independent of the authority-limit trigger.
- 3+ back-and-forth turns with no resolution and no explicit "human" request (README stretch goal) — not implemented in the reference solution; if you add it, verify it doesn't fire on a *productive* 3-turn exchange.
- Order id that doesn't exist in `ORDERS` — `get_order_status` returns `{"error": "order not found"}` — does the agent handle that gracefully or hallucinate order details?
- Quality bar check (from README): would a human reading only `summary` + `requested_action` (without the transcript) have enough to act in under 10 seconds? Worth manually grading a few escalation payloads against this bar.
