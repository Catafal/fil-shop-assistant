import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fil_shop.evaluation_trials import account_results, new_batch, plan_trials, validate_batch


def batch():
    cases = [{"name": "one"}, {"name": "two"}]
    freeze = {"candidate_hash": "a" * 64, "fixture_hash": "b" * 64,
              "versions": {key: "v1" for key in ("model", "prompt", "tool", "voice", "harness", "simulator", "grader")}}
    state = new_batch(cases, 3, freeze, "b" * 64)
    state.update(materialized_cases=cases, test_ids=["t1", "t2"], invocation_id="invoke", agent_id="agent")
    state["planned_trials"] = plan_trials(state)
    return state


def summary():
    return {"id": "invoke", "agent_id": "agent", "runs": [
        {"test_id": test, "test_run_id": f"{test}-{i}", "status": "passed", "credits_used": i}
        for test in ("t1", "t2") for i in range(3)]}


def test_exact_repetitions_keep_actual_ids_usage_and_stable_rank():
    state, result = batch(), summary()
    result["runs"].reverse()
    graded = account_results(state, result)
    assert graded["matrix_validation"] == {"valid": True, "errors": [], "expected_count": 6, "actual_count": 6}
    assert graded["runs"][0]["test_run_id"] == "t2-2"
    assert graded["runs"][0]["trial_index"] == 3
    assert graded["runs"][0]["credits_used"] == 2
    assert "not execution order" in graded["trial_index_semantics"]
    assert len({r["trial_id"] for r in graded["runs"]}) == 6


@pytest.mark.parametrize("mutation", [
    lambda r: r["runs"].pop(),
    lambda r: r["runs"].append(copy.deepcopy(r["runs"][0])),
    lambda r: r["runs"][0].update(test_id="unplanned"),
    lambda r: r["runs"][0].update(test_run_id=None),
    lambda r: r["runs"][0].update(test_run_id=r["runs"][1]["test_run_id"]),
    lambda r: r["runs"][0].update(status="pending"),
    lambda r: r.update(id="wrong"),
])
def test_missing_extra_duplicate_unidentified_pending_results_are_not_deduplicated(mutation):
    result = summary()
    mutation(result)
    expected_count = len(result["runs"])
    result = account_results(batch(), result)
    assert not result["matrix_validation"]["valid"]
    assert len(result["runs"]) == expected_count
    assert all("trial_id" not in r for r in result["runs"])


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(repeat_count=4),
    lambda s: s["freeze"]["versions"].update(model="changed"),
    lambda s: s["materialized_cases"][0].update(name="changed"),
    lambda s: s["test_ids"].reverse(),
    lambda s: s["planned_trials"].pop(),
])
def test_frozen_identity_and_matrix_tampering_rejected(mutation):
    state = batch()
    mutation(state)
    with pytest.raises(ValueError):
        validate_batch(state)


def runner():
    path = Path(__file__).parents[1] / "scripts/provider_tests.py"
    spec = importlib.util.spec_from_file_location("native_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_runner_subset_import_repeat_submission_and_ambiguous_write(tmp_path, monkeypatch):
    module = runner()
    cases = [{"name": "first", "case": {"id": "case-1", "grading": {"outcome": "no_hold"}}},
             {"name": "second", "case": {"id": "case-2"}}]
    source = tmp_path / "cases.json"
    source.write_text(json.dumps(cases))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    fixture = {"source_sha256": source_hash, "cases": cases, "calendar": {},
               "materialized_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()}
    frozen = tmp_path / "fixture.json"
    frozen.write_text(json.dumps(fixture))
    freeze = batch()["freeze"]
    freeze["fixture_hash"] = hashlib.sha256(frozen.read_bytes()).hexdigest()
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze))
    predecessor = tmp_path / "prior.json"
    predecessor.write_text(json.dumps({"agent_id": "old", "cases_sha256": source_hash,
                                      "materialized_sha256": fixture["materialized_sha256"],
                                      "materialized_cases": cases, "test_ids": ["t1", "t2"]}))
    manifest = tmp_path / "new.json"
    client = Mock()
    monkeypatch.setattr(module, "ElevenLabs", lambda **kwargs: client)
    monkeypatch.setattr(module, "load_dotenv", lambda *args: None)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "synthetic")
    base = ["runner", "create", "--agent-id", "agent", "--manifest", str(manifest),
            "--cases", str(source), "--fixture", str(frozen)]
    monkeypatch.setattr("sys.argv", base + ["--freeze", str(freeze_path), "--from-manifest", str(predecessor),
                                          "--case-id", "case-2", "--repeat-count", "3"])
    module.main()
    state = json.loads(manifest.read_text())
    assert state["test_ids"] == ["t2"]
    assert len(state["planned_trials"]) == 3
    client.conversational_ai.tests.create.assert_not_called()
    client.conversational_ai.agents.run_tests.side_effect = TimeoutError("uncertain")
    base[1] = "run"
    monkeypatch.setattr("sys.argv", base)
    with pytest.raises(TimeoutError):
        module.main()
    assert json.loads(manifest.read_text())["pending"]["repeat_count"] == 3
    assert client.conversational_ai.agents.run_tests.call_args.kwargs["repeat_count"] == 3
    assert client.conversational_ai.agents.run_tests.call_args.kwargs["request_options"] == {"max_retries": 0}
    with pytest.raises(SystemExit, match="uncertain"):
        module.main()
    assert client.conversational_ai.agents.run_tests.call_count == 1
    # New cases carry grading metadata locally, never in the provider shopper request.
    fresh = tmp_path / "created.json"
    client.conversational_ai.tests.create.side_effect = [SimpleNamespace(id="new-1"), SimpleNamespace(id="new-2")]
    monkeypatch.setattr("sys.argv", ["runner", "create", "--agent-id", "agent", "--manifest", str(fresh),
                                    "--cases", str(source), "--fixture", str(frozen), "--freeze", str(freeze_path)])
    module.main()
    for call in client.conversational_ai.tests.create.call_args_list:
        assert "case" not in call.kwargs["request"]
    assert "case" in json.loads(fresh.read_text())["materialized_cases"][0]


def test_summary_retains_provider_run_and_cost_without_inventing_missing_values():
    result = runner().summarize(SimpleNamespace(id="inv", agent_id="agent", test_runs=[SimpleNamespace(
        test_id="t", test_name="test", status="passed", condition_result=None, agent_responses=[],
        test_run_id="actual", credits_used=12, conversation_id="conv")]))
    assert result["runs"][0]["test_run_id"] == "actual"
    assert result["runs"][0]["credits_used"] == 12
    assert result["runs"][0]["conversation_id"] == "conv"
    assert result["credits_used"] is None


def test_nested_metadata_is_not_an_unresolved_template():
    from fil_shop.evaluation_cases import materialize_cases
    cases = [{"name": "nested", "case": {"grading": {"expected": {"colour": "navy"}}},
              "simulation_scenario": "Date {{deadline}}"}]
    resolved, _ = materialize_cases(cases)
    assert resolved[0]["case"] == cases[0]["case"]
    assert "{{" not in resolved[0]["simulation_scenario"]
    cases[0]["case"]["grading"]["expected"]["colour"] = "{{unknown}}"
    with pytest.raises(ValueError, match="Unresolved"):
        materialize_cases(cases)


@pytest.mark.parametrize("count", [0, -1, 21, True, 1.5])
def test_repeat_count_obeys_provider_limit(count):
    with pytest.raises(ValueError, match="1 to 20"):
        new_batch([{"name": "case"}], count, batch()["freeze"], "b" * 64)
