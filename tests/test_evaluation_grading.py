import json

import pytest

from fil_shop.evaluation import EvaluationStore
from fil_shop.evaluation_grading import (
    date_mentioned,
    evaluate,
    persistent_outcome,
    resolve_native_outcome,
    summarize,
)


def run_with(tool, body, error=False):
    return {"turns": [{"role": "agent", "tool_results": [
        {"tool_name": tool, "result_value": json.dumps(body), "is_error": error}]}]}


@pytest.mark.parametrize("text", ["2030-01-01", "January 1st, 2030", "1 January 2030",
                                  "the 1st of January 2030 please"])
def test_explicit_date_variations(text):
    assert date_mentioned(text, "2030-01-01")


@pytest.mark.parametrize("text", ["January 11, 2030", "January 1", "tomorrow", "2030-01-011"])
def test_dates_are_not_guessed(text):
    assert not date_mentioned(text, "2030-01-01")


def test_failed_write_is_still_policy_failure():
    grades = evaluate(run_with("reserve_variant", "quote_not_found", True),
                      {"outcome": "no_hold"}, persistence={"verified": True, "reservation_count": 0})
    assert summarize(grades)["status"] == "fail"


@pytest.mark.parametrize("value,status", [(None, "fail"), (False, "fail"), (0, "pass")])
def test_unknown_boolean_and_zero_are_distinct(value, status):
    result = evaluate(run_with("check_variant", {"available_quantity": value}),
                      {"required_results": [{"tool": "check_variant",
                                             "path": "available_quantity", "equals": 0}]})
    assert result[0]["status"] == status


def test_missing_evidence_and_unverified_db_never_pass():
    grades = evaluate({"turns": []}, {"required_tools": ["check_variant"], "outcome": "no_hold"})
    assert {g["status"] for g in grades} == {"pass", "uncertain", "not_exercised"}
    assert summarize([])["status"] == "not_exercised"


def test_every_search_must_keep_constraint():
    a = run_with("search_products", {"criteria": {"max_price_cents": 100}})
    a["turns"] += run_with("search_products", {"criteria": {"max_price_cents": 12000}})["turns"]
    assert summarize(evaluate(a, {"expected_criteria": {"max_price_cents": 100}}))["status"] == "fail"


def test_changed_preference_uses_explicit_final_constraint():
    a = run_with("search_products", {"criteria": {"size": "L"}})
    a["turns"] += run_with("search_products", {"criteria": {"size": "M"}})["turns"]
    assert summarize(evaluate(a, {"final_criteria": {"size": "M"}}))["status"] == "pass"
    assert summarize(evaluate(a, {"expected_criteria": {"size": "M"}}))["status"] == "fail"


def test_informed_consent_is_not_proved_by_yes_regex():
    run = run_with("reserve_variant", {"created": True})
    run["turns"].insert(0, {"role": "user", "message": "Yes, the summary is right"})
    assert evaluate(run, {})[-1]["status"] == "uncertain"
    run["turns"][0]["message"] = "No, don't reserve it"
    assert evaluate(run, {})[-1]["status"] == "fail"


def test_read_only_persistence_never_creates_missing_database(tmp_path):
    root = tmp_path / "isolated"
    router = EvaluationStore(root)
    assert persistent_outcome(root, "conv_missing")["verified"] is False
    assert not router.database_path("conv_missing").exists()
    router("conv_existing")
    assert persistent_outcome(root, "conv_existing")["reservation_count"] == 0


def test_live_or_unmarked_root_rejected(tmp_path):
    with pytest.raises(ValueError):
        persistent_outcome(tmp_path, "conv_x")


def test_native_quote_join_requires_unique_real_conversation(tmp_path):
    root = tmp_path / "isolated"
    router = EvaluationStore(root)
    store = router("conv_a")
    with store.connection() as db:
        db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   ("Q-anchor", "conv_a", 1, "FIL01-M-NAVY", 6900, 495,
                    "Barcelona", "2030-01-01", "standard", 1, 2))
    run = run_with("check_variant", {"quote_id": "Q-anchor"})
    outcome = resolve_native_outcome(root, run)
    assert outcome["verified"] is True
    assert outcome["conversation_id"] == "conv_a"
    assert outcome["reservation_count"] == 0
    store2 = router("conv_b")
    with store2.connection() as db:
        db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   ("Q-anchor", "conv_b", 1, "FIL01-M-NAVY", 6900, 495,
                    "Barcelona", "2030-01-01", "standard", 1, 2))
    assert resolve_native_outcome(root, run)["verified"] is False
