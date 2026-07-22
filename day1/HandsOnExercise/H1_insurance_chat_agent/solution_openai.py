"""
H1 — Insurance Chat Agent with Citations (GPT-5.x mini VARIANT)

Same task as solution.py (retrieve policy clauses, answer ONLY from context,
force citations, reject hallucinated doc_ids) — reimplemented on the OpenAI
SDK to show the same agentic pattern is provider-agnostic. Structured output
is enforced via Pydantic + Responses API `response_format` instead of
Anthropic's forced tool_choice.

Setup:
    pip install openai
    Set OPENAI_API_KEY in .env (see repo root .env for the placeholder).

Model: gpt-5-mini (contents.md "Models" row: GPT-5.x mini).
"""

import json
import os
import re
import sys
from typing import List
from pydantic import BaseModel, Field, ValidationError
from openai import OpenAI

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY not set. Add it to .env at the repo root, then "
        "re-run (`pip install openai` if you haven't already)."
    )

client = OpenAI()
MODEL = "gpt-5-mini"

with open("knowledge_base.json") as f:
    KB = json.load(f)

STOPWORDS = {"the", "is", "a", "an", "of", "to", "for", "my", "does", "do",
             "what", "how", "if", "and", "on", "in", "it", "am", "i"}


class GroundedAnswer(BaseModel):
    """Typed shape for a grounded answer — identical contract to the
    Anthropic version, so the two solutions are directly comparable."""
    answer: str = Field(description="Direct answer to the customer's question, using ONLY the retrieved context.")
    citations: List[str] = Field(description="doc_ids (e.g. 'POL-002') that support the answer. Empty list if not grounded.")
    can_resolve: bool = Field(description="True if the context had enough information to answer; False if this is a fallback.")


def _tokenize(text: str):
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def retrieve(question: str, top_k: int = 2):
    q_tokens = set(_tokenize(question))
    scored = []
    for doc in KB:
        doc_tokens = set(_tokenize(doc["title"] + " " + doc["text"]))
        score = len(q_tokens & doc_tokens)
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in scored[:top_k] if score > 0]


def build_grounded_prompt(question: str, docs: list) -> str:
    if not docs:
        context_block = "(no matching policy clauses found)"
    else:
        context_block = "\n\n".join(
            f"[{d['id']}] {d['title']}\n{d['text']}" for d in docs
        )
    return f"""Context (retrieved policy clauses):
{context_block}

Customer question: {question}

Instructions:
- Answer using ONLY the context above. Do not use outside insurance knowledge.
- List every doc_id you relied on in `citations`.
- If the context does not contain the answer, set can_resolve to False and
  set answer to "I don't have this information in the policy documents I can access."
- Keep the answer to 2-3 sentences."""


def answer_question(question: str) -> GroundedAnswer:
    docs = retrieve(question)
    valid_ids = {d["id"] for d in docs}
    prompt = build_grounded_prompt(question, docs)

    response = client.responses.parse(
        model=MODEL,
        instructions=(
            "You are a policy Q&A assistant for an insurance company's "
            "support team. You must never answer from general knowledge — "
            "only from the context provided in the user message."
        ),
        input=prompt,
        text_format=GroundedAnswer,
    )

    result = response.output_parsed
    if result is None:
        raise RuntimeError("Model refused or returned no parsed output.")

    # Defense in depth: same hallucinated-citation check as the Anthropic version.
    bad_citations = [c for c in result.citations if c not in valid_ids]
    if bad_citations:
        raise RuntimeError(f"Model cited doc(s) not in retrieved context: {bad_citations}")

    return result


if __name__ == "__main__":
    test_questions = [
        "How many days do I have to file a two-wheeler claim after an accident?",
        "If I make one claim this year, what happens to my No Claim Bonus?",
        "Is my pet's vet bill covered under my health policy?",
    ]
    for q in test_questions:
        print(f"\nQ: {q}")
        result = answer_question(q)
        print(result.model_dump_json(indent=2))

# Expected behavior: identical to solution.py's Anthropic version —
# Q1 -> citations=["POL-001"], can_resolve=True.
# Q2 -> citations=["POL-002"], can_resolve=True.
# Q3 -> citations=[], can_resolve=False.
# Compare this file to solution.py side-by-side: retrieve(), the prompt
# builder, and the citation-validation logic are byte-for-byte the same —
# only the model call and the structured-output mechanism differ.
