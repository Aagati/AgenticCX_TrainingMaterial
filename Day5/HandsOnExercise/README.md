# Day 5 — Training Exercises
## Agentic AI Program · Evaluating & Operating CX Agents

This folder contains the six hands-on labs referenced in the Day 5 deck and
the Trainer & Participant Guide. Each lab has its own folder with everything
needed to run it: instructions, starter files, sample data, and (where
applicable) a facilitator-only solution.

**Facilitators:** files named `*_solution.py` or `*_SOLUTION.xlsx` are
reference answers — don't hand these to participants before the lab.
Everything else is participant-facing.

---

## Pre-Lunch — Concepts & Patterns

| Folder | Lab | Industry | Format |
|---|---|---|---|
| `01_Prelunch_H1_Insurance_Eval_Suite` | Resolution + Trajectory Eval Suite | Insurance | Python |
| `02_Prelunch_H2_Banking_Online_QA` | Online QA with Sentiment + Escalation | Banking | Python |
| `03_Prelunch_H3_Retail_ROI_Model` | CX ROI Model | Retail | Excel |

## Post-Lunch — Applied Lab

| Folder | Lab | Industry | Format |
|---|---|---|---|
| `04_Postlunch_H1_Banking_Governance_Pack` | Governance Pack | Banking | Word template |
| `05_Postlunch_H2_Insurance_Eval_Gate` | Eval-Gated Rollout | Insurance | Python |
| `06_Postlunch_H3_Team_Capstone_Brief` | Capstone Scoping | Team Exercise | Word template |

---

## Running the Python labs

Each Python lab folder has a `*_starter.py` (what participants fill in) and
a `*_solution.py` (facilitator reference). Both read their data file from
the same folder, so run them from inside the lab's own directory:

```bash
cd 01_Prelunch_H1_Insurance_Eval_Suite
python eval_suite_starter.py      # participant version — raises NotImplementedError until filled in
python eval_suite_solution.py     # facilitator reference — runs end-to-end
```

No API keys or external packages are required — every lab is self-contained
and runs on the Python standard library.

## Running the Excel lab

Open `Retail_ROI_Calculator_TEMPLATE.xlsx` directly in Excel (or Google
Sheets / LibreOffice Calc). The `Retail_ROI_Calculator_SOLUTION.xlsx` in the
same folder is the facilitator reference with every formula filled in.

## Using the Word templates

`Governance_Pack_Template.docx` and `Capstone_Brief_Template.docx` are
fill-in-the-blank documents — yellow boxes are where participants type.
Each includes a worked example in an appendix, filled in for a *different*
scenario than the one participants are asked to complete, so it can guide
without being copyable.

---

## Supplementary files (added after reviewer feedback)

Three files were added after the initial release, in response to a technical
review. They are **additive** — the original Word/Excel deliverables are
still the primary artifact for their labs — for teams who also want a
programmatic version:

| File | Adds to | What it does |
|---|---|---|
| `03_Prelunch_H3_Retail_ROI_Model/roi_formula.py` | Lab H3 (Retail ROI) | Same net-savings formula as the Excel workbook, in Python — useful if you want to wire it to live telemetry later (e.g. Day 8). Requires no dependencies beyond the standard library. |
| `04_Postlunch_H1_Banking_Governance_Pack/agent_card_schema.py` | Lab H1 (Governance Pack) | A typed (Pydantic) version of the Agent Card, so it can be validated in CI/CD and rendered to markdown automatically. Requires `pip install pydantic`. |
| `05_Postlunch_H2_Insurance_Eval_Gate/eval_gate_cicd.py` | Lab H2 (Eval Gate) | A CLI wrapper around the eval-gate logic with proper process exit codes (0/1/2), ready to drop into a GitHub Actions or Bitbucket pipeline step. No new dependencies. |

**A correction:** building `roi_formula.py` as an independent cross-check
surfaced two real bugs in the original `Retail_ROI_Calculator_SOLUTION.xlsx`
/ `_TEMPLATE.xlsx` — a formula referencing the wrong Inputs row (pulling
"Agent-handled AHT" instead of "Agent cost per contact"), and a CSAT-floor
check that was actually comparing baseline CSAT against live CSAT instead of
live CSAT against the floor. Both are now fixed in the workbooks in this
package: the correct monthly savings figure for the example scenario is
**$58,800/month ($705,600/year)**, not the $17,760 shown in earlier copies.
If you downloaded this package before this note was added, please
re-download the Excel files.

---

## How each lab ties back to the day's topics

- **H1 Insurance (AM)** → Topic 1, CX Evaluation
- **H2 Banking (AM)** → Topic 2, Continuous QA (+ Topic 3, Observability)
- **H3 Retail (AM)** → Topic 4, ROI
- **H1 Banking (PM)** → Topic 3 (PM), Governance Pack — building on Topic 5 (AM), Governance
- **H2 Insurance (PM)** → Topic 2 (PM), Eval-Gated Rollout — building on H1 (AM)'s eval suite
- **H3 Team Exercise (PM)** → Topic 5 (PM), Capstone Framing

See the Trainer & Participant Guide for the full timing schedule and
facilitator notes for each topic.
