# Pre-Lunch · H3 — Retail: CX ROI Model

**Track:** Retail | **Time box:** 20–30 min | **Ships:** a completed ROI workbook + a one-paragraph business case
**Pattern practiced:** formula-driven business case with a hard quality gate (CSAT floor)

## Objective
Using the given baseline data for a retail order-status/returns/delivery support agent, build a working ROI model in Excel — every result must be a **formula**, not a typed-in number — and produce a one-paragraph business case with a CSAT quality guardrail.

## Steps
1. Open `Retail_ROI_Calculator_TEMPLATE.xlsx`. Read the Instructions sheet fully before touching a formula.
2. Review the Inputs sheet — this is your given data. Do not change it.
3. On the ROI Model sheet, fill in each yellow cell with a formula referencing the Inputs sheet (guidance for each formula is in column C — delete the guidance text once you've filled in the cell).
4. Check the CSAT floor check cell reads **PASS**. If it reads **FAIL**, do not report a savings number — say why in your summary instead.
5. Confirm the Summary sheet's auto-generated sentence reads correctly once every ROI Model cell is filled in.
6. As a stretch goal, add a sensitivity row: what resolution rate would be needed to break even if the agent's build & run cost doubled?

## Run
Open `Retail_ROI_Calculator_TEMPLATE.xlsx` directly in Excel (or Google Sheets / LibreOffice Calc). `Retail_ROI_Calculator_SOLUTION.xlsx` in the same folder is the facilitator reference with every formula filled in.

A programmatic cross-check of the same net-savings formula is also available:
```bash
cd 03_Prelunch_H3_Retail_ROI_Model
python roi_formula.py
```

## What "ships" means
A completed `Retail_ROI_Calculator_TEMPLATE.xlsx` with no yellow cells left blank, and a Summary sheet business-case sentence you could read aloud to a sponsor.

## Files
- `Retail_ROI_Calculator_TEMPLATE.xlsx` — the lab itself: 4 sheets (Instructions, Inputs, ROI Model with blank yellow formula cells, Summary with an auto-text sentence).
- `Retail_ROI_Calculator_SOLUTION.xlsx` — facilitator reference, same workbook with every formula filled in.
- `build_workbooks.py` — the generator script that produces both `.xlsx` files via `openpyxl`; not part of the lab itself, only needed if the workbooks need to be regenerated.
- `roi_formula.py` — **supplementary, added after reviewer feedback.** A Python port of the same net-savings formula from the workbook, for teams who also want a programmatic version (e.g. to wire to live telemetry later). No dependencies beyond the standard library. Also doubles as a hand-checkable sanity check for the Excel solution: for the sample inputs (volume 20,000; human AHT 9.5 min; human cost $28/hr; agent resolution 72%; agent cost $0.35/contact; CSAT live 4.1, floor 4.0) it asserts monthly savings of **$58,800** ($705,600/year).

## Facilitator tips
- Watch for participants hardcoding a computed number instead of writing the formula — that's the single most common shortcut, and it defeats the point of the exercise (the model should update if inputs change).
- If a pair's PASS/FAIL cell reads FAIL, that's a valid and useful outcome — walk them through what they'd say to a sponsor instead of a savings figure.

## Stretch goal (optional)
Add a sensitivity row: what resolution rate would be needed to break even if the agent's build & run cost doubled? Not built into either workbook — a genuine open-ended exercise.
