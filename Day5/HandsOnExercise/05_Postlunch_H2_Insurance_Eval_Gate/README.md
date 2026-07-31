# Post-Lunch · H2 — Insurance: Eval-Gated Rollout

**Track:** Insurance | **Time box:** 25–35 min | **Ships:** a working release gate with PASS/BLOCKED verdicts
**Pattern practiced:** zero-override safety gate, direct sequel to lab 01's eval suite

## Objective
Using the baseline resolution rate from this morning's Insurance lab and three simulated candidate agent versions, implement a gate that blocks a release if it regresses resolution rate below baseline, **OR** has any safety violation — and prove your gate behaves correctly by running all three candidates through it.

## Steps
1. Open `candidate_versions.json`. Note the baseline resolution rate, and skim the three candidates — try to predict which will pass before you write any code.
2. In `eval_gate_starter.py`, implement `resolution_rate()` and `safety_violation_count()`.
3. Implement `evaluate_gate()` with the two block conditions described in the file's docstring. Make sure a candidate that fails **both** conditions reports both reasons, not just the first one found.
4. Run `python eval_gate_starter.py` and check your verdicts against your Step 1 predictions.
5. Confirm: `v2.1` should **PASS**, `v2.2` should **BLOCK** on resolution, `v2.3` should **BLOCK** on safety. If your output disagrees, debug before moving on.

## Run
```bash
cd 05_Postlunch_H2_Insurance_Eval_Gate
python eval_gate_starter.py      # participant version — raises NotImplementedError until the 3 TODOs are filled in
python eval_gate_solution.py     # facilitator reference — runs end-to-end
```
No API keys or external packages required.

## What "ships" means
A working `eval_gate_starter.py` that prints a clear PASS/BLOCKED verdict with reasons for each of the three candidates.

## Files
- `goldens.json` — carried over from lab 01, referenced for context on the baseline agent.
- `candidate_versions.json` — a `baseline` resolution rate plus three `candidates`, each with a `results` list of per-conversation `resolved`/`safety_violation` outcomes.
- `eval_gate_starter.py` — 3 TODOs (`resolution_rate`, `safety_violation_count`, `evaluate_gate`).
- `eval_gate_solution.py` — facilitator reference.
- `eval_gate_cicd.py` — **supplementary, added after reviewer feedback.** Wraps `eval_gate_solution.py`'s gate logic for a real CI/CD pipeline: checks ONE candidate named on the command line and exits with a status code a pipeline can branch on (`0` = approved, `1` = blocked, `2` = unknown candidate).
  ```bash
  python eval_gate_cicd.py --candidate v2.1-candidate
  echo $?
  ```
  This file deliberately does not call any LLM API — everything it checks is already computed and stored in `candidate_versions.json`, exactly as in the classroom version. A production pipeline would generate that data by actually running the candidate agent against the golden set, which is separate infrastructure, not something to bolt onto a training exercise.

## Facilitator tips
- The most common bug: only checking the first condition and returning early, so a candidate that fails **both** resolution AND safety only reports one reason. Watch for it.
- Use the stretch goal (a resolution-rate tolerance band) to spark a real discussion: a tolerance makes the gate less brittle to noise, but also means a real regression could slip through under the tolerance line. There's no single right answer here.

## Stretch goal (optional)
Right now the resolution-rate comparison is a hard `>= baseline` check. Add a small configurable tolerance (e.g. gate fails only if the drop is more than 2 percentage points) and discuss with your table: what's the risk of adding that tolerance?
