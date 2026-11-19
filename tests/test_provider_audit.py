import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit", ROOT / "scripts/audit_provider_results.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_evaluator_pass_cannot_replace_real_inventory_error():
    findings = module.audit({"runs": [{"name": "Fil inventory-failure", "status": "passed",
                                      "turns": []}]})
    assert "Fil inventory-failure: no successful search evidence" in findings
    assert "Fil inventory-failure: actual inventory failure absent" in findings


def test_refusal_case_rejects_even_unsuccessful_reservation_attempt():
    findings = module.audit({"runs": [{"name": "Fil summary-not-consent", "status": "passed",
                                      "turns": [{"tool_results": [{
                                          "tool_name": "reserve_variant", "is_error": True,
                                          "result_value": "quote_not_found"}]}]}]})
    assert "Fil summary-not-consent: unexpected reservation attempt" in findings


def test_unrequested_internal_reference_and_unobserved_quote_are_detected():
    findings = module.audit({"runs": [{"name": "Fil reservation", "status": "passed", "turns": [
        {"role": "agent", "message": None, "tool_results": [{
            "tool_name": "reserve_variant", "is_error": False,
            "result_value": '{"created":true,"reservation":{"id":"RES-ABC","quote_id":"Q1"}}',
        }]},
        {"role": "agent", "message": "La referència és RES-ABC", "tool_results": []},
    ]}]})
    assert "Fil reservation: internal reservation ID spoken without request" in findings
    assert "Fil reservation: reservation not grounded in observed quote" in findings


def test_evaluator_pass_rejects_internal_planning_as_customer_message():
    findings = module.audit({"runs": [{"name": "Fil delivery-unknown", "status": "passed",
                                      "turns": [{"role": "agent", "message":
                                                 "Let's call check_variant with requested_date.",
                                                 "tool_results": []}]}]})
    assert "Fil delivery-unknown: internal tool/planning text in customer response" in findings


def test_refusal_without_summary_confirmation_is_unexercised():
    findings = module.audit({"runs": [{"name": "Fil summary-not-consent", "status": "passed",
                                      "turns": [{"role": "user", "message": "No, do not reserve anything",
                                                 "tool_results": []}]}]})
    assert "Fil summary-not-consent: exact summary-yes then separate consent-no path unexercised" in findings


def test_missing_date_cannot_be_supplied_only_by_agent():
    findings = module.audit({"runs": [{"name": "Fil missing-date", "status": "passed", "turns": [
        {"role": "agent", "message": "I'll use2030-01-01", "tool_results": []},
        {"role": "agent", "message": None, "tool_results": [{"tool_name": "check_variant",
         "is_error": False, "result_value": '{"requested_date":"2030-01-01","quote_id":"Q"}'}]},
    ]}]})
    assert "Fil missing-date: caller clarification before actual check unexercised" in findings
