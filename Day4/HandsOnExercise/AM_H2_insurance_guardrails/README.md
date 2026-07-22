# AM · H2 — Insurance: Guardrails + Prompt-Injection Defence, Then Attack It

**Track:** Insurance | **Time box:** ~40 min | **Pattern practiced:** layered input/output filters; treating retrieved content as untrusted

## Scenario
Your insurance agent retrieves policy clauses from a knowledge base to
answer questions (the Day 1 grounding pattern). But what if one of those
"policy clauses" was tampered with — or a customer pastes injected
instructions into their message? Today you build defenses against both,
then try to break your own defenses.

## Part 1 — Build two guardrail layers
These are **plain Python functions — no API key needed** for this part.
1. `input_guardrail(user_message: str) -> dict` — scans for prompt-injection
   patterns (e.g. "ignore previous instructions", "you are now", "system:",
   "new instructions:", attempts to make the agent reveal its system
   prompt). Returns `{"flagged": bool, "reason": str or None}`.
2. `output_guardrail(agent_reply: str) -> dict` — scans the agent's
   OUTPUT for signs the injection worked: does the reply contain anything
   that looks like a leaked system prompt, or comply with an instruction
   that didn't come from the legitimate system prompt (e.g. it starts
   discussing something wildly off-topic for an insurance agent, or
   repeats back injected text verbatim). Returns the same shape.

Run both against `test_cases.json` (a mix of clean and adversarial inputs)
and report precision: how many of the adversarial cases were caught, and
whether any clean cases were incorrectly flagged (false positives matter
too — an overly aggressive filter blocks real customers).

## Part 2 — Wire it into a real agent, then attack it
**This part needs an API key.** Build `protected_reply(user_message,
retrieved_doc)` that:
1. Runs `input_guardrail` on `user_message` — if flagged, refuse before
   ever calling the model.
2. Calls Claude with a system prompt instructing it to treat
   `retrieved_doc` strictly as untrusted reference data, never as
   instructions (this is the Day 1 grounding discipline, now framed
   explicitly as a security boundary, not just an accuracy one).
3. Runs `output_guardrail` on the reply — if flagged, return a generic
   safe fallback instead of the model's actual output.

Then **attack it**: feed `protected_reply` the malicious documents in
`malicious_kb_docs.json` (policy clauses with injected instructions buried
in them) and see whether your guardrails catch the attempt.

## Why this matters
This is today's Topic 03 (guardrails) and Topic 04 (prompt injection):
the core discipline is treating your OWN knowledge base and customer
input as untrusted, the same way a web application treats user input as
untrusted by default. A single filter is never bulletproof — that's why
this is called **layered** defense: input filtering, an explicit
untrusted-data framing in the prompt, and output filtering are three
independent chances to catch an attack that gets past the others.

## Files
- `test_cases.json` — clean and adversarial messages for Part 1.
- `malicious_kb_docs.json` — policy clauses with injected instructions for Part 2.
- `starter.py` — scaffold with TODOs.
- `solution.py` — reference solution.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals
- Add a case to `malicious_kb_docs.json` that your current guardrails
  DON'T catch, and see what it takes to catch it — this is exactly the
  iterative red-teaming loop a real guardrail stack goes through.
- Log every flagged attempt (input or output) to a list, the seed of a
  security-incident audit trail (this previews this afternoon's Topic 03,
  Defence-in-Depth).

## Discussion (bring back to the group)
- Your input guardrail catches injection attempts in the CUSTOMER's
  message. Why do you also need an output guardrail, if the input looks
  clean? (Hint: where did the malicious instructions in Part 2 actually
  come from.)
