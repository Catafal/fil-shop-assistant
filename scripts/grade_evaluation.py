"""Grade frozen native trial output without collapsing uncertain/unexercised outcomes."""

import argparse
import hashlib
import json
from pathlib import Path

from fil_shop.evaluation_grading import evaluate, resolve_native_outcome, summarize
from fil_shop.evaluation_trials import account_results, validate_batch


def report(manifest, results, root, contracts=None):
    validate_batch(manifest)
    results = account_results(manifest, results)
    cases = {c.get("case", {}).get("id", c["name"]): c for c in manifest["materialized_cases"]}
    rows = []
    for run in results["runs"]:
        case = cases.get(run.get("case_id"))
        if case is None or not results["matrix_validation"]["valid"]:
            rows.append({"test_run_id": run.get("test_run_id"), "status": "harness_invalid",
                         "reason": "No unambiguous planned case mapping"})
            continue
        metadata = case.get("case", {})
        contract = metadata.get("grading") or (contracts or {}).get(run["case_id"])
        persistence = resolve_native_outcome(root, run)
        grades = evaluate(run, contract or {}, persistence=persistence)
        summary = summarize(grades)
        rows.append({"case_id": run["case_id"], "trial_id": run["trial_id"],
                     "test_run_id": run["test_run_id"], "provider_status": run["status"],
                     "provider_credits": run.get("credits_used"), "status": summary["status"],
                     "grades": grades, "persistence": persistence,
                     "semantic_review": "pending independent review",
                     "contract_present": contract is not None})
    return {"schema": 1, "batch_id": manifest["batch_id"], "freeze": manifest["freeze"],
            "matrix_validation": results.get("matrix_validation"), "trials": rows,
            "planned_count": len(manifest["planned_trials"]), "returned_count": len(results["runs"]),
            "provider_completed_count": sum(r["status"] in ("passed", "failed") for r in results["runs"]),
            "objective_counts": {status: sum(r["status"] == status for r in rows)
                                 for status in ("pass", "fail", "uncertain", "not_exercised", "harness_invalid")},
            "acceptance": "not inferred from objective grades; independent semantic review required"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, help="Frozen external contracts for legacy regressions")
    args = parser.parse_args()
    value = report(json.loads(args.manifest.read_text()), json.loads(args.results.read_text()),
                   args.evaluation_root,
                   json.loads(args.contracts.read_text())["contracts"] if args.contracts else None)
    if args.contracts:
        value["contracts_sha256"] = hashlib.sha256(args.contracts.read_bytes()).hexdigest()
    with args.output.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    print(json.dumps(value["objective_counts"]))
