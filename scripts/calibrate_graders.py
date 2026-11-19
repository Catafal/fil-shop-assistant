"""Report agreement with versioned provisional controls, never human accuracy."""

import argparse
import hashlib
import json
from pathlib import Path

from fil_shop.evaluation_grading import VERSION, date_mentioned, evaluate, summarize


def calibrate(corpus):
    observations = []
    for control in corpus["controls"]:
        grades = evaluate(control["run"], control["contract"], persistence=control["persistence"])
        if control.get("criterion"):
            grades = [g for g in grades if g["criterion"] == control["criterion"]]
        observations.append({"id": control["id"], "expected": control["expected"],
                             "actual": summarize(grades)["status"], "grades": grades})
    for i, control in enumerate(corpus["date_controls"]):
        observations.append({"id": f"date-{i}",
                             "expected": "pass" if control["expected"] else "fail",
                             "actual": "pass" if date_mentioned(control["text"], control["iso"])
                             else "fail"})
    disagreements = [o for o in observations if o["expected"] != o["actual"]]
    return {"grader_version": VERSION, "corpus_version": corpus["version"],
            "reference_label_provenance": corpus["reference_label_provenance"],
            "control_count": len(observations), "agreement_count": len(observations)-len(disagreements),
            "false_accept_count": sum(o["actual"] == "pass" and o["expected"] != "pass"
                                      for o in observations),
            "false_reject_count": sum(o["actual"] != "pass" and o["expected"] == "pass"
                                      for o in observations),
            "disagreements": disagreements, "observations": observations,
            "semantic_judge_accuracy": "unverified; no independent human-labelled corpus"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("agent/grader-calibration-v2.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.corpus.read_bytes()
    report = calibrate(json.loads(raw))
    report["corpus_sha256"] = hashlib.sha256(raw).hexdigest()
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("control_count", "agreement_count",
                                           "false_accept_count", "false_reject_count")}))
    raise SystemExit(bool(report["disagreements"]))
