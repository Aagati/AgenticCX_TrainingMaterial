# -*- coding: utf-8 -*-
"""
BONUS TIER A - Red Team Challenge

There is NO solution file for this part. That's deliberate - same
convention as Day4/HandsOnExercise/Capstone_Banking_MCP_Agent's Part 4.

Six novel attack techniques in red_team_kb_docs.json, none of which the
required Part 5 guardrails (guardrails.py's INSTRUCTION_INJECTION_PATTERNS)
are designed to catch - they were built after those patterns, specifically
to miss them. Your job: extend the defense in your_defense_layer() below.

The grading signal here is judgment, not the raw score. A low score with
a clear write-up of WHY a technique is hard to catch (and what it would
cost in false positives to catch it) is worth more than a high score with
no reasoning. See bonus/README.md for the discussion questions a
facilitator will actually grade you against.

Setup: no API key needed - this scores against static text, offline.
Run: python red_team_challenge.py
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Your Part 5 guardrails.py lives in starter/ (or solution/, if you're a
# facilitator checking this), a sibling of this bonus/ folder - add it to
# the path so `from guardrails import ...` resolves without copying files.
_STARTER_DIR = Path(__file__).resolve().parent.parent / "starter"
if _STARTER_DIR.exists() and str(_STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(_STARTER_DIR))

from guardrails import layer_strip_control_chars, layer_detect_instruction_injection  # noqa: E402

with open(Path(__file__).parent / "red_team_kb_docs.json", encoding="utf-8") as f:
    RED_TEAM_DOCS = json.load(f)


def your_defense_layer(text: str) -> dict:
    """Starts as a passthrough to the Part 5 baseline (control-char
    stripping + the given instruction-injection patterns). Rewrite this
    freely: add new regex patterns, a length/repetition heuristic (for
    RT-03's token-stuffing), a homoglyph-normalization pass (for RT-05),
    a check that scans for JSON-shaped tool_result payloads embedded in
    plain text (for RT-02), anything you want.

    There's no reference implementation to match - the point is to try
    something, see what it catches and misses, and be able to explain
    both. Return {"flagged": bool, "reason": str | None}, same shape as
    every other guardrail layer in this course.
    """
    control_result = layer_strip_control_chars(text)
    if control_result["flagged"]:
        return control_result
    return layer_detect_instruction_injection(text)


def score() -> None:
    caught = 0
    for doc in RED_TEAM_DOCS:
        result = your_defense_layer(f"{doc['title']} {doc['text']}")
        status = "CAUGHT" if result["flagged"] else "MISSED"
        if result["flagged"]:
            caught += 1
        print(f"[{status}] {doc['doc_id']} ({doc['attack_type']})"
              + (f" - {result['reason']}" if result["flagged"] else ""))
    print(f"\n{caught}/{len(RED_TEAM_DOCS)} caught.")
    print("Bring this to your facilitator with notes on each miss: why is it "
          "hard to catch with a text-only filter, and what's the false-positive "
          "risk of the fix you'd reach for?")


if __name__ == "__main__":
    score()

# Discussion prompts (bring these back to the group, per bonus/README.md):
#   - RT-03 stuffs the exact vocabulary your OWN retrieve() scores on. Can
#     you defend against retrieval-poisoning-by-relevance without changing
#     the scoring function itself?
#   - RT-04 sits at a rank your sanitize_retrieved_docs() (Part 5) should
#     already reach, since it scans every retrieved doc, not just doc[0].
#     If your defense still misses it, is the gap in WHAT you scan or WHAT
#     you scan FOR?
#   - RT-05's homoglyph attack defeats any check keyed on the exact string
#     "apply_billing_credit". What's the tradeoff between Unicode
#     normalization (NFKC folding, confusable-character detection) and the
#     risk of false-flagging a legitimately multilingual customer message?
