"""
H1 — Insurance Chat Agent with Citations (STARTER)

Design note: we validate the model's citations two ways — first with a
Pydantic schema (does the shape match at all?), then with a business-logic
check (does every cited doc_id actually appear in what we retrieved?).
Schema validation catches malformed output; the second check catches
plausible-looking but hallucinated citations that a schema alone can't see.
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
    """TODO 1: Define three fields:
      - answer: str
      - citations: List[str]
      - can_resolve: bool
    Add a short Field(description=...) to each — the description text is
    what the model actually reads when deciding how to fill the field in,
    so it's not just documentation, it's part of the prompt.
    """
    pass


SUBMIT_ANSWER_TOOL = {
    "name": "submit_grounded_answer",
    "description": "Submit the final answer with its supporting citations.",
    "input_schema": GroundedAnswer.model_json_schema(),
}


def _tokenize(text: str):
    """Given to you — lowercase, keep alphabetic words, drop stopwords and
    very short tokens. Retrieval quality isn't the point of this exercise,
    so don't spend time here."""
    words = re.findall(r"[a-z]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def retrieve(question: str, top_k: int = 2):
    """
    TODO 2: Return the top_k documents from KB most relevant to `question`,
    using keyword overlap:
      1. token-set for the question via _tokenize().
      2. token-set for each doc via _tokenize(doc["title"] + " " + doc["text"]).
      3. score = size of the set intersection.
      4. sort by score descending, take top_k, and keep only score > 0
         (zero overlap must return [] — that's what triggers the
         "I don't have this information" path later).
    Return a list of dicts (the KB doc objects themselves).
    """
    raise NotImplementedError


def build_grounded_prompt(question: str, docs: list) -> str:
    """
    TODO 3: Build the user-turn prompt: include each retrieved doc's id,
    title, and text; instruct the model to answer ONLY from the provided
    context and to list every doc_id it relied on. No need to mention
    citation FORMAT (like brackets) anymore — the tool schema handles that.
    """
    raise NotImplementedError


def answer_question(question: str) -> GroundedAnswer:
    """
    TODO 4:
      1. retrieve() docs, and collect valid_ids = the set of retrieved doc ids.
      2. Call client.messages.create with tools=[SUBMIT_ANSWER_TOOL] and
         tool_choice={"type": "tool", "name": "submit_grounded_answer"} —
         this FORCES the model to respond via the tool, not free text.
      3. Extract the tool_use block, construct a GroundedAnswer(**tool_call.input)
         inside a try/except ValidationError — raise a clear error on failure.
      4. Check every citation is in valid_ids; raise an error if any aren't
         (a hallucinated citation should never reach the customer silently).
      5. Return the validated GroundedAnswer.
    """
    raise NotImplementedError


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
