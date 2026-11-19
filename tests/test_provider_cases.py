import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from elevenlabs.conversational_ai.tests.types.tests_create_request_body import (
    TestsCreateRequestBody_Simulation as SimulationCase,
)

ROOT = Path(__file__).resolve().parents[1]


def test_native_cases_are_bounded_and_use_real_tools():
    cases = json.loads((ROOT / "agent/test-cases.json").read_text())
    assert len({case["name"] for case in cases}) == 11
    for case in cases:
        SimulationCase.model_validate(case)
        assert case["tool_mock_config"]["mocking_strategy"] == "none"
        assert 1 <= case["simulation_max_turns"] <= 16


def test_evidence_projection_drops_tool_headers_and_reasoning():
    spec = importlib.util.spec_from_file_location("provider_tests", ROOT / "scripts/provider_tests.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    turn = SimpleNamespace(model_dump=lambda **_: {
        "role": "agent", "message": "Resultat",
        "tool_calls": [{"headers": {"Authorization": "must-not-save"}}],
        "reasoning": "must-not-save", "tool_results": [],
    })
    response = SimpleNamespace(id="run", agent_id="agent", test_runs=[SimpleNamespace(
        test_id="test", test_name="test", status="passed", condition_result=None,
        agent_responses=[turn],
    )])
    result = module.summarize(response)
    assert "must-not-save" not in json.dumps(result)
    assert result["runs"][0]["turns"][0]["message"] == "Resultat"


def test_calendar_materialization_is_future_and_conflict_is_deliberate():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from fil_shop.evaluation_cases import materialize_cases
    cases = json.loads((ROOT / "agent/test-cases.json").read_text())
    resolved, calendar = materialize_cases(cases, datetime(2026, 12, 25, 23, tzinfo=ZoneInfo("Europe/Madrid")))
    assert calendar["deadline"] == "2027-01-08"
    assert calendar["weekday"] == "Friday"
    assert calendar["wrong_weekday"] != calendar["weekday"]
    assert "{{" not in json.dumps(resolved)
    assert cases != resolved


def test_shared_fixture_rejects_changed_cases_or_source():
    import hashlib

    import pytest

    from fil_shop.evaluation_cases import validate_fixture
    cases = [{"name": "same-date", "simulation_scenario": "2030-01-01"}]
    fixture = {"source_sha256": "source", "cases": cases, "calendar": {},
               "materialized_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()}
    assert validate_fixture(fixture, "source") is fixture
    with pytest.raises(ValueError, match="different scenario"):
        validate_fixture(fixture, "other")
    cases[0]["simulation_scenario"] = "2030-01-02"
    with pytest.raises(ValueError, match="was changed"):
        validate_fixture(fixture, "source")
