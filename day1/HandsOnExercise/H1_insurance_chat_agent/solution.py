"""
H1 — Insurance Chat Agent with Citations (REFERENCE SOLUTION)
"""

import json
import re
from typing import List
from pydantic import BaseModel, Field, ValidationError
from anthropic import Anthropic

client = Anthropic()
MODEL = "claude-sonnet-5"

with open("knowledge_base.json") as f:
    KB = json.load(f)

STOPWORDS = {"the", "is", "a", "an", "of", "to", "for", "my", "does", "do",
             "what", "how", "if", "and", "on", "in", "it", "am", "i"}


class GroundedAnswer(BaseModel):
    """Typed shape for a grounded answer — makes 'cite your sources' a
    machine-checkable contract instead of a hope that the model formats
    citations correctly in free text."""
    answer: str = Field(description="Direct answer to the customer's question, using ONLY the retrieved context.")
    citations: List[str] = Field(description="doc_ids (e.g. 'POL-002') that support the answer. Empty list if not grounded.")
    can_resolve: bool = Field(description="True if the context had enough information to answer; False if this is a fallback.")


SUBMIT_ANSWER_TOOL = {
    "name": "submit_grounded_answer",
    "description": "Submit the final answer with its supporting citations.",
    "input_schema": GroundedAnswer.model_json_schema(),
}


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

    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=(
            "You are a policy Q&A assistant for an insurance company's "
            "support team. You must never answer from general knowledge — "
            "only from the context provided in the user message."
        ),
        tools=[SUBMIT_ANSWER_TOOL],
        tool_choice={"type": "tool", "name": "submit_grounded_answer"},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_call = next(b for b in response.content if b.type == "tool_use")
    try:
        result = GroundedAnswer(**tool_call.input)
    except ValidationError as e:
        # The model's output didn't match our schema — fail loud, not silent.
        raise RuntimeError(f"Model returned a malformed answer: {e}")

    # Defense in depth: even a schema-valid response could cite a doc_id
    # that was never actually retrieved (a hallucinated citation). Catch it
    # here rather than trusting the model's self-report.
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

# Expected behavior:
# Q1 -> citations=["POL-001"], can_resolve=True (48 hours to intimate).
# Q2 -> citations=["POL-002"], can_resolve=True (NCB resets to 0%).
# Q3 -> citations=[], can_resolve=False -> "I don't have this information..."
# Every citation is validated against the actually-retrieved doc_ids before
# being trusted — a hallucinated citation raises an error instead of
# silently reaching the customer.
