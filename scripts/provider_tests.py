"""Create, run or inspect native simulations. Each write requires operator authorization."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from fil_shop.evaluation_cases import validate_fixture
from fil_shop.evaluation_trials import (
    account_results,
    case_id,
    new_batch,
    plan_trials,
    validate_batch,
)


def summarize(response):
    """Keep observable behavior; never retain request headers or internal reasoning."""
    result = {"id": response.id, "agent_id": response.agent_id, "credits_used": getattr(response, "credits_used", None), "runs": []}
    for run in response.test_runs:
        item = {
            "test_id": run.test_id, "name": run.test_name, "status": run.status,
            "condition": run.condition_result.model_dump() if run.condition_result else None,
            "test_run_id": getattr(run, "test_run_id", None),
            "credits_used": getattr(run, "credits_used", None),
            "conversation_id": getattr(run, "conversation_id", None),
            "turns": [],
        }
        for turn in run.agent_responses or []:
            data = turn.model_dump(exclude_none=True)
            item["turns"].append({
                "role": data.get("role"), "message": data.get("message"),
                "agent_metadata": data.get("agent_metadata"),
                "rag_retrieval_info": data.get("rag_retrieval_info"),
                "tool_results": [
                    {k: tool.get(k) for k in ("tool_name", "is_error", "result_value")}
                    for tool in data.get("tool_results", [])
                ],
            })
        result["runs"].append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "run", "status"])
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cases", type=Path, default=Path("agent/test-cases.json"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fixture", type=Path, help="Shared frozen date/case artifact for compared models")
    parser.add_argument("--repeat-count", type=int, default=None)
    parser.add_argument("--freeze", type=Path, help="Frozen candidate/fixture hashes and version identities")
    parser.add_argument("--from-manifest", type=Path, help="Reuse existing tests in a NEW batch; preserve predecessor")
    parser.add_argument("--case-id", action="append", help="Select a subset by stable case ID (repeatable)")
    args = parser.parse_args()
    load_dotenv(".env")
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    digest = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    existed = args.manifest.exists()
    state = json.loads(args.manifest.read_text()) if existed else {
        "agent_id": args.agent_id, "cases_sha256": digest, "test_ids": [],
    }
    if state["agent_id"] != args.agent_id or state["cases_sha256"] != digest:
        raise SystemExit("Manifest belongs to a different agent or case version.")
    if args.action in ("create", "run"):
        fixture_path = args.fixture or (Path(state["fixture_path"]) if state.get("fixture_path") else None)
        if fixture_path is None:
            raise SystemExit("Create/run needs a shared frozen --fixture artifact")
        fixture = validate_fixture(json.loads(fixture_path.read_text()), digest)
        if state.get("materialized_sha256") not in (None, fixture["materialized_sha256"]):
            raise SystemExit("Manifest fixture differs from shared comparison artifact")
        state["fixture_path"] = str(fixture_path.resolve())
    if not existed:
        if args.action != "create" or not args.freeze:
            raise SystemExit("New batches require create, --freeze and --fixture")
        cases = fixture["cases"]
        if args.case_id:
            selected = set(args.case_id)
            if len(selected) != len(args.case_id) or selected - {case_id(c) for c in cases}:
                raise SystemExit("Subset case IDs are duplicated or unknown")
            cases = [c for c in cases if case_id(c) in selected]
        predecessor = None
        if args.from_manifest:
            old = json.loads(args.from_manifest.read_text())
            if old.get("schema_version") == 2:
                validate_batch(old)
            if old.get("pending"):
                raise SystemExit("Predecessor has an ambiguous write; reconcile first")
            if old["cases_sha256"] != digest or old.get("materialized_sha256") != fixture["materialized_sha256"]:
                raise SystemExit("Reused tests must belong to the identical case/fixture version")
            old_cases = old.get("materialized_cases", [])
            if len(old_cases) != len(old["test_ids"]):
                raise SystemExit("Predecessor tests are incomplete")
            mapping = {case_id(c): tid for c, tid in zip(old_cases, old["test_ids"], strict=True)}
            if len(mapping) != len(old_cases) or not {case_id(c) for c in cases} <= mapping.keys():
                raise SystemExit("Predecessor lacks selected case identities")
            state["test_ids"] = [mapping[case_id(c)] for c in cases]
            predecessor = {"path": str(args.from_manifest.resolve()),
                           "sha256": hashlib.sha256(args.from_manifest.read_bytes()).hexdigest()}
        state.update(new_batch(cases, args.repeat_count if args.repeat_count is not None else 1,
                               json.loads(args.freeze.read_text()),
                               hashlib.sha256(fixture_path.read_bytes()).hexdigest(), predecessor))
        state.update(materialized_cases=cases, calendar=fixture["calendar"],
                     materialized_sha256=fixture["materialized_sha256"])
    elif args.from_manifest or args.case_id:
        raise SystemExit("Subset/import options require a new manifest")
    if state.get("schema_version") == 2:
        validate_batch(state)
        if args.repeat_count is not None and args.repeat_count != state["repeat_count"]:
            raise SystemExit("Repeat count is frozen; create a new linked manifest")
        if args.freeze and json.loads(args.freeze.read_text()) != state["freeze"]:
            raise SystemExit("Candidate freeze changed")
        if args.action in ("create", "run") and hashlib.sha256(fixture_path.read_bytes()).hexdigest() != state["freeze"]["fixture_hash"]:
            raise SystemExit("Exact fixture artifact changed")
    elif args.repeat_count not in (None, 1) or args.freeze:
        raise SystemExit("Legacy manifests retain repeat_count=1; create a linked v2 batch")
    if state.get("pending"):
        raise SystemExit("Previous write outcome uncertain; reconcile with provider before retrying.")

    def save():
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.manifest.with_suffix(args.manifest.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(args.manifest)

    if args.action == "create":
        save()
        if "materialized_cases" not in state:
            state["materialized_cases"], state["calendar"] = fixture["cases"], fixture["calendar"]
            state["materialized_sha256"] = fixture["materialized_sha256"]
            save()
        cases = state["materialized_cases"]
        for case in cases[len(state["test_ids"]):]:
            state["pending"] = {"create_test": case["name"]}
            save()
            test = client.conversational_ai.tests.create(
                request={key: value for key, value in case.items() if key != "case"}, request_options={"max_retries": 0},
            )
            state["test_ids"].append(test.id)
            state.pop("pending")
            save()
        if state.get("schema_version") == 2:
            state["planned_trials"] = plan_trials(state)
            save()
        print(f"Saved {len(state['test_ids'])} native tests; none executed.")
    elif args.action == "run":
        if state.get("invocation_id"):
            raise SystemExit("This manifest already has a run; use status, not a duplicate run.")
        if len(state["test_ids"]) != len(state["materialized_cases"]):
            raise SystemExit("Create all cases first.")
        if state.get("schema_version") == 2:
            state["planned_trials"] = plan_trials(state)
        state["pending"] = {"run_tests": state["test_ids"], "repeat_count": state.get("repeat_count", 1)}
        save()
        result = client.conversational_ai.agents.run_tests(
            args.agent_id, tests=[{"test_id": tid} for tid in state["test_ids"]],
            name="Fil shop integration", repeat_count=state.get("repeat_count", 1),
            request_options={"max_retries": 0},
        )
        state["invocation_id"] = result.id
        state.pop("pending")
        save()
        print("Started invocation", result.id)
    else:
        if not state.get("invocation_id") or not args.output:
            raise SystemExit("Status needs a completed run submission and --output.")
        if args.output.exists():
            raise SystemExit("Evidence output already exists; use a new snapshot path")
        result = client.conversational_ai.tests.invocations.get(state["invocation_id"])
        summary = summarize(result)
        if state.get("schema_version") == 2:
            summary = account_results(state, summary)
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        for name in ("ELEVENLABS_API_KEY", "FIL_WEBHOOK_SECRET", "FIL_EVALUATION_WEBHOOK_SECRET",
                     "TELECAT_WEBHOOK_SECRET"):
            if os.getenv(name):
                text = text.replace(os.environ[name], "<redacted>")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
        for run in result.test_runs:
            print(run.test_name, run.status)
        if state.get("schema_version") == 2 and not summary["matrix_validation"]["valid"]:
            raise SystemExit("Incomplete/invalid trial matrix; raw evidence preserved, not accepted")


if __name__ == "__main__":
    try:
        main()
    except ApiError as error:
        # Provider errors can contain submitted bodies. Keep diagnostics free of secrets.
        raise SystemExit(f"Provider returned HTTP {error.status_code}; inspect manifest/readback.")
