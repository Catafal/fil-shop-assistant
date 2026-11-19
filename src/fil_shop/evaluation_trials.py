"""Immutable native trial plans and strict result accounting; no provider operations."""
import hashlib
import json
import uuid
from collections import Counter

VERSION_KEYS = {"model", "prompt", "tool", "voice", "harness", "simulator", "grader"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def case_id(case):
    return case.get("case", {}).get("id", case["name"])


def new_batch(cases, repeat_count, freeze, fixture_hash, predecessor=None):
    if type(repeat_count) is not int or not 1 <= repeat_count <= 20:
        raise ValueError("repeat_count must be an integer from 1 to 20")
    if not VERSION_KEYS <= freeze.get("versions", {}).keys() or any(
        not isinstance(freeze["versions"][key], str) or not freeze["versions"][key].strip()
        for key in VERSION_KEYS
    ):
        raise ValueError("Freeze requires explicit model/prompt/tool/voice/harness/simulator/grader versions")
    for key in ("candidate_hash", "fixture_hash"):
        value = freeze.get(key, "")
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"Freeze requires SHA256 {key}")
    if freeze["fixture_hash"] != fixture_hash:
        raise ValueError("Freeze fixture_hash differs from exact fixture file")
    ids = [case_id(case) for case in cases]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Cases must have nonempty unique identities")
    batch = {"schema_version": 2, "batch_id": str(uuid.uuid4()), "repeat_count": repeat_count,
             "freeze": freeze, "predecessor": predecessor,
             "case_versions": [{"case_id": case_id(case), "case_hash": digest(case)} for case in cases]}
    batch["batch_identity_hash"] = digest(batch)
    return batch


def validate_batch(state):
    identity = {key: state[key] for key in ("schema_version", "batch_id", "repeat_count", "freeze",
                                           "predecessor", "case_versions")}
    if digest(identity) != state["batch_identity_hash"]:
        raise ValueError("Immutable batch identity changed")
    if state["case_versions"] != [{"case_id": case_id(c), "case_hash": digest(c)}
                                  for c in state["materialized_cases"]]:
        raise ValueError("Frozen case content changed")
    if "planned_trials" in state and state["planned_trials"] != plan_trials(state):
        raise ValueError("Frozen trial plan changed")


def plan_trials(state):
    cases, ids = state["case_versions"], state["test_ids"]
    if len(ids) != len(cases) or len(set(ids)) != len(ids):
        raise ValueError("Provider test identities must be complete and unique")
    return [{"trial_id": f"{state['batch_id']}:{index}:{repetition}",
             "case_id": case["case_id"], "case_hash": case["case_hash"], "test_id": test_id,
             "trial_index": repetition}
            for index, (case, test_id) in enumerate(zip(cases, ids, strict=True))
            for repetition in range(1, state["repeat_count"] + 1)]


def account_results(state, summary):
    """Never deduplicate; bind rank slots only once the entire matrix is identifiable."""
    validate_batch(state)
    expected = Counter(item["test_id"] for item in state["planned_trials"])
    actual = Counter(run["test_id"] for run in summary["runs"])
    errors = []
    if summary["id"] != state["invocation_id"] or summary["agent_id"] != state["agent_id"]:
        errors.append("invocation_or_agent_mismatch")
    if actual != expected:
        errors.append("case_repetition_matrix_mismatch")
    ids = [run.get("test_run_id") for run in summary["runs"]]
    if any(not isinstance(value, str) or not value for value in ids):
        errors.append("missing_test_run_id")
    if len(set(ids)) != len(ids):
        errors.append("duplicate_test_run_id")
    if any(run["status"] not in ("passed", "failed", "cancelled") for run in summary["runs"]):
        errors.append("unfinished_or_unknown_status")
    summary.update({"batch_id": state["batch_id"], "batch_identity_hash": state["batch_identity_hash"],
                    "freeze": state["freeze"], "planned_trials": state["planned_trials"],
                    "matrix_validation": {"valid": not errors, "errors": errors,
                                          "expected_count": sum(expected.values()), "actual_count": len(ids)},
                    "trial_index_semantics": "lexicographic test_run_id rank within case; not execution order"})
    if not errors:
        for test_id in expected:
            runs = sorted((r for r in summary["runs"] if r["test_id"] == test_id), key=lambda r: r["test_run_id"])
            slots = [slot for slot in state["planned_trials"] if slot["test_id"] == test_id]
            for run, slot in zip(runs, slots, strict=True):
                run.update(slot)
    return summary
