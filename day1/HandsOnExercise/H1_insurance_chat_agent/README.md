# H1 — Insurance: Chat Agent that Answers Policy Questions with Citations

**Track:** Insurance | **Time box:** 40 min | **Pattern practiced:** Retrieve → Ground → Answer with citations

## Scenario
You work on the CX engineering team for an insurance company. Customers ask
policy questions ("How long is my claim window?", "What's my NCB after one
claim?"). Support agents currently answer these by manually searching a PDF
of policy wordings — slow, and prone to wrong answers when they misremember
a clause.

## Your task
Build a single-turn chat agent that:
1. Takes a customer question.
2. Retrieves the most relevant clause(s) from `knowledge_base.json` (a small
   set of policy documents — treat this as your knowledge base; no vector DB
   needed at this scale, keyword/TF-based retrieval is fine).
3. Calls Claude with **only the retrieved clauses** in context (not the whole
   KB) and asks it to answer **using only that context**.
4. Returns an answer that **cites the source document id** (e.g. `POL-002`)
   for every factual claim, and says "I don't have this information" if the
   retrieved clauses don't answer the question — it must NOT invent an
   answer from general knowledge.

## Why this matters (tie back to today's concepts)
- This is the **retrieve → act(answer) → confirm** slice of the agentic CX
  loop (Topic 03), stripped down to a single step.
- Citation-forcing is our first concrete **grounding** technique (Topic 04) —
  it's what turns a chatbot into something a compliance team will sign off on.

## Files
- `knowledge_base.json` — 6 sample policy clauses across motor and health.
- `starter.py` — scaffold with TODOs. Run it, it will error/stub until you
  fill in the three TODOs.
- `solution.py` — reference solution (don't peek until you've had a real go,
  or you're stuck for >15 min).

## A note on the output format
The answer is returned as a **Pydantic-validated structure** (`GroundedAnswer`:
`answer`, `citations`, `can_resolve`), not free text with inline `[POL-002]`-style
brackets. The model submits its answer via a forced tool call whose schema
comes straight from the Pydantic model (`GroundedAnswer.model_json_schema()`),
and the code validates every citation against what was actually retrieved
before trusting it. This is the same "typed tool" discipline used in
enterprise integrations — a schema the model must conform to, checked in
code, not just requested in a prompt.

## Setup
```bash
pip install anthropic pydantic
export ANTHROPIC_API_KEY=sk-...
python starter.py
```

## Stretch goals (if you finish early)
- Handle a question that spans two clauses (e.g. "If I file a claim on my
  bike, does that affect my premium next year?" touches both claim filing
  and NCB).
- Add a confidence check: if retrieval score is below a threshold, skip the
  Claude call entirely and return "I don't have this information" — cheaper
  and safer.
- Log every (question, retrieved_ids, answer) triple to a JSON file — this is
  the seed of an eval set you'll build on Day 4.

## Discussion (bring back to the group)
- What happens to answer quality if you retrieve the *wrong* clause but a
  *plausible-sounding* one? Try it — pick a question and feed the model an
  unrelated clause. Does it still cite confidently?

---

## Alt-stack variant (optional)
`solution_openai.py` — the identical grounded-citation task, reimplemented
on the OpenAI SDK (GPT-5.x mini, structured output via `responses.parse`)
instead of Anthropic. Same `retrieve()`/prompt/citation-validation logic —
diff the two files to see what changes provider-to-provider and what
doesn't. Needs `OPENAI_API_KEY` (see repo-root `.env` and
`requirements-multisdk.txt`).
