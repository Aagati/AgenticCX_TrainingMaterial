# Day 5 — Evaluation, QA, ROI, Governance

No agent code here — Day 5 measures what Days 1-4 built. Pre-lunch labs are
pure Python stdlib (01, 02) or Excel (03) — zero API calls, everything scored
offline against fixed JSON fixtures. Post-lunch H1/H3 are Word-template
fill-ins (no code); H2 is Python again, a direct sequel to lab 01.

Run each Python lab from INSIDE its own folder (`cd` first — they read data
files relative to their own directory):
```
cd Day5_Training_Exercises/Day5_Training_Exercises/01_Prelunch_H1_Insurance_Eval_Suite
../../../.venv/Scripts/python.exe eval_suite_solution.py
```

---

## 01 — Insurance: Resolution + Trajectory Eval Suite
`01_Prelunch_H1_Insurance_Eval_Suite/` · scores conversations against goldens, NO model calls

**Structure**
- `resolution_score()` — trivial 1/0 cast of `expected_resolution`.
- `trajectory_score()` — the real logic, 4 branches:
  1. Exact action-sequence match → `1.0`.
  2. Any expected action MISSING from actual → hard `0.0`.
  3. All present but OUT OF ORDER (checked via `dict.fromkeys()` dedup so a harmless REPEAT isn't mistaken for an order violation) → hard `0.0`.
  4. Correct + complete but with EXTRA/redundant calls → soft penalty `min(0.15*extra, 0.3)`, capped, not zeroed.
- `combined_score()` — fixed weighted blend `0.6*resolution + 0.4*trajectory`.
- `run_report()` — table + `flag_threshold=0.6` gate + suite-level aggregate (resolution rate, avg trajectory score).

**Test matrix** (against `goldens.json` — exact IDs/values depend on the fixture, verify against the file directly)

| # | Case shape | Expected `trajectory_score` |
|---|---|---|
| 1 | `agent_actions == expected_actions` exactly | `1.0` |
| 2 | `expected_actions` has an action NOT present in `agent_actions` | `0.0` (hard fail — missing required step) |
| 3 | Same actions as expected but different ORDER (e.g. disclosure before identity verify) | `0.0` (hard fail — sequencing violation) |
| 4 | All expected actions present, correctly ordered, plus 2 extra/redundant calls | `1.0 - min(0.15*2, 0.3)` = `0.70` |
| 5 | Combined score < `flag_threshold=0.6` | Row printed with `⚑ REVIEW`, appears in the "Flagged for human review" list |

**Edge cases to cover**
- A conversation with a REPEATED required action (e.g. `verify_identity` called twice, harmless) vs. one with a genuinely OUT-OF-ORDER required action — confirm the dedup logic in branch 3 correctly tells these apart; this is the trickiest line in the file, worth tracing by hand once.
- `expected_actions` is an empty list (nothing required) — does `trajectory_score` degrade gracefully, or does the exact-match branch make this trivially `1.0` regardless of `agent_actions`?
- README/docstring note: participants' OWN scoring rules don't need to match this exactly — what matters is they can JUSTIFY their weighting and trajectory logic. Good discussion: what would change if trajectory outweighed resolution (0.4/0.6 instead of 0.6/0.4)? When would that flip make sense?

---

## 02 — Banking: Online QA with Sentiment + Escalation
`02_Prelunch_H2_Banking_Online_QA/` · lexicon sentiment trend + escalation cross-check, NO model calls

**Structure**
- `turn_sentiment()` — bag-of-words against 2 hardcoded sets (`POSITIVE_WORDS`/`NEGATIVE_WORDS`), returns -1/0/1 via count comparison. Deliberately NOT an LLM classifier — cheap and deterministic.
- `sentiment_trend()` — filters to `speaker == "customer"` turns only; agent's own text never scored.
- `has_sharp_negative_shift()` — single pass checking CONSECUTIVE-turn drop `trend[i-1] - trend[i] >= 2` — catches a jump straight to strongly negative, not just "any negative turn anywhere."
- `run_report()`'s key structural point: computes `escalated_but_not_flagged` — conversations that escalated but did NOT trip the sentiment heuristic — printed as "still worth reviewing," proving resolution/sentiment/escalation are 3 INDEPENDENT signals, deliberately not folded into one score.

**Test matrix** (against `conversations.json`)

| # | Check | Expected |
|---|---|---|
| 1 | `turn_sentiment("thanks, that's really helpful!")` | `1` (positive words outweigh negative) |
| 2 | `turn_sentiment("this is ridiculous, so frustrating")` | `-1` |
| 3 | `turn_sentiment("okay, I understand")` | `0` (no lexicon hits either way) |
| 4 | A conversation trend like `[0, -1, -2]` (gradual decline, no single sharp jump ≥2) | `has_sharp_negative_shift` → `False` |
| 5 | A conversation trend like `[1, -1]` (positive to negative in one turn, diff=2) | `has_sharp_negative_shift` → `True` |
| 6 | A conversation with `escalated=True` but sentiment stayed calm throughout | Appears in `escalated_but_not_flagged`, NOT in `flagged_sentiment` |

**Edge cases to cover**
- Message with BOTH positive and negative lexicon words in equal count ("thanks, but this is still frustrating") — `pos == neg` → returns `0` (neutral) — is that the right call, or should mixed sentiment be its own category?
- A word that appears in neither set but is clearly emotionally loaded in context (lexicon coverage gap) — construct a test message with obvious frustration using NONE of the hardcoded words, confirm the method misses it. Good live demo of bag-of-words' ceiling vs. an LLM-based sentiment check.
- `sentiment_trend` on a conversation with ONLY agent turns, no customer turns — returns `[]`; confirm `has_sharp_negative_shift([])` doesn't index-error on the empty list.
- README's own throughline: don't let trainees "fix" this by merging all 3 signals into 1 score — the lab's actual lesson is keeping them separate, contrast directly against lab 01's `combined_score` design choice.

---

## 03 — Retail: CX ROI Model (Excel)
`03_Prelunch_H3_Retail_ROI_Model/` · `build_workbooks.py` is a GENERATOR script, not the lab itself

**Structure**
- `build_workbooks.py` produces 2 files via `openpyxl`: `Retail_ROI_Calculator_TEMPLATE.xlsx` (yellow cells blank, for participants) and `..._SOLUTION.xlsx` (formulas filled in) — same `build(is_template, out_path)` function branches on a bool to decide whether formula cells get blanked or populated.
- Real lab work happens INSIDE Excel — 4 sheets: Instructions, Inputs (blue-on-teal, locked given data), ROI Model (yellow formula cells), Summary (auto-text via cell-concatenation formula).
- Python never evaluates the formulas — no correctness-checking happens outside Excel itself.

**Test matrix** (verify formulas in the SOLUTION workbook's ROI Model sheet)

| # | Cell | Formula | Expected given the sample Inputs (vol=20000, human AHT=9.5min, human $28/hr, resolution=72%, agent AHT=3.2min, agent cost=$0.35/contact, CSAT live=4.1, floor=4.0) |
|---|---|---|---|
| 1 | B5 Human cost/contact | `=(Inputs!B6/60)*Inputs!B7` | `(9.5/60)*28` ≈ `$4.43` |
| 2 | B6 Contacts resolved by agent | `=Inputs!B5*Inputs!B8` | `20000*0.72` = `14,400` |
| 3 | B8 Baseline cost (100% human) | `=Inputs!B5*B5` | `20000*4.43` ≈ `$88,667` |
| 4 | B12 CSAT floor check | `=IF(Inputs!B11>=Inputs!B12,"PASS","FAIL")` | `4.1 >= 4.0` → `"PASS"` |
| 5 | B13 Annualised savings | `=B10*12` | Only trust this number if B12 = PASS |

**Edge cases to cover**
- Change `Inputs!B11` (live CSAT) to below the floor (e.g. 3.8) — confirm B12 flips to `"FAIL"` and that the Summary sheet's auto-text still renders (it references B12's text value directly) — does the business-case sentence still read sensibly when the gate fails, or does it silently keep touting the savings number?
- A participant HARDCODES a number instead of a formula in a yellow cell (the #1 rule violation called out in the Instructions sheet) — the workbook won't visibly break, but the model stops updating if Inputs change. Worth demonstrating: change an Input after a hardcoded fill-in and show the ROI Model doesn't move.
- Sensitivity check (stretch goal): what resolution rate breaks even if agent build/run cost doubles? Not built into either workbook — a genuine open-ended Excel exercise.
- Cross-check the TEMPLATE has ALL yellow cells actually blank (no accidental formula leakage from the generator script) before handing it to participants — run `build(True, ...)` and manually spot-check a few ROI Model cells.

---

## 05 — Insurance: Eval-Gated Rollout
`05_Postlunch_H2_Insurance_Eval_Gate/` · CI/CD-style promotion gate, direct sequel to lab 01

**Structure**
- `evaluate_gate()` — TWO independent block conditions: `cand_rate < baseline_resolution_rate` (regression) OR `violations > 0` (any safety violation, zero-tolerance, explicitly NO override). Either alone is sufficient to BLOCK — NOT blended into one score (opposite of lab 01's `combined_score` — here a safety violation can't be averaged away by good resolution numbers).
- `reasons` — list accumulates ALL failed-condition strings, not just the first; supports multiple simultaneous failure reasons in one printout.
- File's own docstring states the expected verdict per candidate up front — doubles as its own test oracle.

**Test matrix** (from `candidate_versions.json`, per the file's own documented expectations)

| # | Candidate | Resolution rate | Safety violations | Expected verdict |
|---|---|---|---|---|
| 1 | `v2.1-candidate` | ≥ baseline | 0 | `PASS` |
| 2 | `v2.2-candidate` | 60% (< 80% baseline) | 0 | `BLOCKED` — reason: resolution regression |
| 3 | `v2.3-candidate` | 100% | 2 | `BLOCKED` — reason: safety violations, DESPITE perfect resolution |

**Edge cases to cover**
- Construct a candidate that fails BOTH conditions at once (regression AND violations) — confirm `reasons` lists BOTH strings, not just one (the code appends independently, doesn't short-circuit on the first hit).
- A candidate that exactly TIES the baseline resolution rate (`cand_rate == baseline_resolution_rate`) — the check is strict `<`, so a tie should `PASS` — confirm that boundary condition explicitly, it's an easy off-by-one to get wrong when reimplementing.
- README's own framing: this is meant to be run as a GATE, not just a report — walk through what wiring this into an actual CI step would look like (exit code on BLOCKED, etc.) even though the reference script only prints. Good bridge from "eval script" to "eval-gated rollout" as an actual engineering practice.
- Candidate with `results` list that's empty (no test cases run at all) — `resolution_rate()` divides by `len(results)` — confirm this doesn't raise `ZeroDivisionError` before trusting the gate on a misconfigured candidate.

---

## 04 — Banking: Governance Pack (Word template, no code)
`04_Postlunch_H1_Banking_Governance_Pack/` · fill-in-the-blank `.docx`, yellow boxes = participant input

**What to check when facilitating**
- Worked example in the appendix uses a DIFFERENT scenario than what participants must complete — verify the appendix scenario doesn't accidentally overlap enough to be directly copyable.
- No code to test here — the "cases to cover" are governance-content cases: does the template prompt for things like decision authority, escalation paths, and rollback triggers, not just describe the system.

## 06 — Team Capstone Brief (Word template, no code)
`06_Postlunch_H3_Team_Capstone_Brief/` · scoping exercise, same template pattern as 04

**What to check when facilitating**
- Same anti-copy design (worked example ≠ participant scenario) as both the Governance Pack and the Excel TEMPLATE/SOLUTION split in lab 03 — consistent pattern across all 3 non-code deliverables in this course.
- Ties together Topic 5 (PM) capstone framing — verify the brief forces a scoping decision (what's IN vs. explicitly OUT of the capstone), not just a feature list.
