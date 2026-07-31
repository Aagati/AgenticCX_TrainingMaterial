"""
Day 5 · Post-Lunch Lab H2 (Insurance) — Eval Gate, CI/CD-Wrapped
====================================================================
SUPPLEMENTARY FILE — added in response to reviewer feedback.

eval_gate_solution.py answers "does this candidate pass?" for all
candidates at once, as a readable report — that's the right shape for
the classroom exercise. This file wraps the same logic for a real
CI/CD pipeline: it checks ONE candidate, named on the command line,
and exits with a status code a pipeline can branch on.

USAGE
-----
    python eval_gate_cicd.py --candidate v2.1-candidate
    echo $?                          # 0 = approved, 1 = blocked

Wire this into a pipeline step (illustrative, not a working file):

    # .github/workflows/deploy.yml  (illustrative)
    # - name: Eval gate
    #   run: python eval_gate_cicd.py --candidate ${{ env.CANDIDATE_VERSION }}
    #   # a non-zero exit here fails the workflow step automatically,
    #   # so the deploy job never runs for a blocked candidate.

A note on scope: this file deliberately does NOT call any LLM API.
Everything it checks (resolution rate, safety-violation count) is
already computed and stored in candidate_versions.json, exactly as in
the classroom version of this lab. A production pipeline would
generate that data by actually running the candidate agent against
the golden set — which is a bigger, separate piece of infrastructure,
not something to bolt onto a training exercise.
"""

import argparse
import sys
import json

# Reuse the facilitator solution's scoring logic (and data path) rather than duplicating it.
from eval_gate_solution import load_data, evaluate_gate, CANDIDATES_PATH


def main():
    parser = argparse.ArgumentParser(description="CI/CD eval gate for a single candidate agent version.")
    parser.add_argument("--candidate", required=True, help="Candidate version name, e.g. v2.1-candidate")
    parser.add_argument("--data", default=CANDIDATES_PATH, help="Path to candidate data file")
    args = parser.parse_args()

    data = load_data(args.data)
    baseline_rate = data["baseline"]["resolution_rate"]

    candidate = next((c for c in data["candidates"] if c["version"] == args.candidate), None)
    if candidate is None:
        print(f"ERROR: no candidate named '{args.candidate}' found in {args.data}", file=sys.stderr)
        sys.exit(2)  # distinct exit code: configuration error, not a gate failure

    verdict = evaluate_gate(baseline_rate, candidate)

    print(json.dumps({
        "version": verdict["version"],
        "verdict": verdict["verdict"],
        "resolution_rate": verdict["resolution_rate"],
        "safety_violations": verdict["safety_violations"],
        "reasons": verdict["reasons"],
    }, indent=2))

    if verdict["verdict"] == "BLOCKED":
        sys.exit(1)  # non-zero -> pipeline step fails -> deploy job does not run
    sys.exit(0)


if __name__ == "__main__":
    main()
