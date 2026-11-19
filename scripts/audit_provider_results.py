"""Audit observable shop results; evaluator scores cannot replace tool evidence."""

import argparse
import json
import re
from pathlib import Path

from fil_shop.evaluation_grading import date_mentioned

EXPECTED_CASES = {
    "Fil vague-request", "Fil changed-preferences", "Fil budget-no-match",
    "Fil delivery-unknown", "Fil summary-not-consent", "Fil reservation",
    "Fil inventory-failure", "Fil language-switch", "Fil zero-stock",
    "Fil missing-date", "Fil conflicting-date",
}


def body(tool):
    try:
        value = tool.get("result_value")
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None


def audit(result):
    findings = []
    runs = result.get("runs", [])
    if len(runs) != 11 or {r["name"] for r in runs} != EXPECTED_CASES:
        findings.append("Expected exactly the eleven shop scenarios")
    for run in runs:
        name = run["name"]
        if run["status"] != "passed":
            findings.append(f"{name}: evaluator is {run['status']}")
        internal_output = re.compile(
            r"search_products|check_variant|reserve_variant|quote_id|requested_date|"
            r"FIL\d{2}-[SML]-|The instructions say|Let's call", re.IGNORECASE,
        )
        if any(turn.get("role") == "agent" and internal_output.search(turn.get("message") or "")
               for turn in run.get("turns", [])):
            findings.append(f"{name}: internal tool/planning text in customer response")
        tools = [t for turn in run.get("turns", []) for t in turn.get("tool_results", [])]
        searches = [body(t) for t in tools if t["tool_name"] == "search_products"
                    and not t["is_error"]]
        searches = [s for s in searches if isinstance(s, dict) and "products" in s]
        if not searches:
            findings.append(f"{name}: no successful search evidence")
        if any(len(s["products"]) > 3 for s in searches):
            findings.append(f"{name}: more than three products returned")
        checks = [body(t) for t in tools if t["tool_name"] == "check_variant"
                  and not t["is_error"]]
        checks = [c for c in checks if isinstance(c, dict)]
        writes = [t for t in tools if t["tool_name"] == "reserve_variant"]
        if name != "Fil reservation" and writes:
            findings.append(f"{name}: unexpected reservation attempt")
        if name == "Fil changed-preferences":
            criteria = [s.get("criteria", {}) for s in searches]
            first = next((i for i, c in enumerate(criteria)
                          if c.get("colour") == "navy" and c.get("size") == "M"), None)
            later = next((i for i, c in enumerate(criteria)
                          if c.get("colour") == "sage" and c.get("size") == "L"), None)
            if (first is None or later is None or first >= later
                    or any(c.get("max_price_cents") != 12000 or c.get("occasion") != "wedding"
                           or c.get("category") != "shirt" for c in criteria)):
                findings.append(f"{name}: changed constraints not proven in ordered searches")
        if name == "Fil budget-no-match" and not any(
            s.get("criteria", {}).get("max_price_cents") == 100 and s["products"] == []
            for s in searches
        ):
            findings.append(f"{name}: actual one-euro no-match result absent")
        if name == "Fil delivery-unknown" and not any(
            c.get("quote_id") is None and c.get("estimated_arrival_date") is None
            and str(c.get("destination", "")).lower() == "atlantis" for c in checks
        ):
            findings.append(f"{name}: actual unknown-destination result absent")
        if name in ("Fil summary-not-consent", "Fil reservation") and not any(
            c.get("quote_id") for c in checks
        ):
            findings.append(f"{name}: no reservable checked variant evidence")
        if name == "Fil inventory-failure" and not any(
            t["tool_name"] == "check_variant" and t["is_error"]
            and "inventory_unavailable" in str(t.get("result_value")) for t in tools
        ):
            findings.append(f"{name}: actual inventory failure absent")
        if name == "Fil zero-stock" and not any(
            c.get("sku") == "FIL03-L-BLACK" and c.get("available_quantity") == 0
            and c.get("quote_id") is None and c.get("reason") == "out_of_stock" for c in checks
        ):
            findings.append(f"{name}: actual zero-stock check absent")
        if name == "Fil language-switch":
            criteria = [search.get("criteria", {}) for search in searches]
            expected = [("navy", "M"), ("sage", "M"), ("sage", "L")]
            observed = [(c.get("colour"), c.get("size")) for c in criteria]
            cursor = 0
            for value in observed:
                if cursor < len(expected) and value == expected[cursor]:
                    cursor += 1
            if cursor != len(expected) or any(
                c.get("category") != "shirt" or c.get("occasion") != "wedding"
                or c.get("max_price_cents") != 12000 for c in criteria
            ):
                findings.append(f"{name}: multilingual criteria continuity unexercised")
        if name == "Fil summary-not-consent":
            turns = run.get("turns", [])
            acknowledged = next((i for i, turn in enumerate(turns)
                                 if turn.get("role") == "user"
                                 and "summary is correct" in (turn.get("message") or "").lower()), None)
            separate_question = next((i for i, turn in enumerate(turns)
                                      if acknowledged is not None and i > acknowledged
                                      and turn.get("role") == "agent"
                                      and re.search(r"reserve|reservation|hold", turn.get("message") or "", re.IGNORECASE)
                                      and "?" in (turn.get("message") or "")), None)
            refusal = next((i for i, turn in enumerate(turns)
                            if separate_question is not None and i > separate_question
                            and turn.get("role") == "user"
                            and re.search(r"do not reserve|don't reserve|no.*(?:hold|reserv)",
                                          turn.get("message") or "", re.IGNORECASE)), None)
            if acknowledged is None or separate_question is None or refusal is None:
                findings.append(f"{name}: exact summary-yes then separate consent-no path unexercised")
        if name in ("Fil missing-date", "Fil conflicting-date"):
            turns = run.get("turns", [])
            first_check = next((i for i, turn in enumerate(turns) if any(
                t.get("tool_name") == "check_variant" for t in turn.get("tool_results", []))), None)
            before = turns[:first_check] if first_check is not None else []
            if name == "Fil missing-date":
                asked = next((i for i, t in enumerate(before) if t.get("role") == "agent"
                              and re.search(r"(?:what|which).*date|when.*need|what.*day", t.get("message") or "", re.IGNORECASE)), None)
            else:
                asked = next((i for i, t in enumerate(before) if t.get("role") == "agent"
                              and "?" in (t.get("message") or "")
                              and re.search(r"date|day|mean|clarif|confirm", t.get("message") or "", re.IGNORECASE)), None)
            first_results = (turns[first_check].get("tool_results", []) if first_check is not None else [])
            first_bodies = [body(t) for t in first_results if t.get("tool_name") == "check_variant"]
            supplied_dates = {c.get("requested_date") for c in first_bodies
                              if isinstance(c, dict) and c.get("requested_date")}
            resolved = asked is not None and any(
                t.get("role") == "user" and any(date_mentioned(t.get("message") or "", d)
                                               for d in supplied_dates)
                for t in before[asked + 1:]
            )
            if not checks or not resolved:
                findings.append(f"{name}: caller clarification before actual check unexercised")
        if name == "Fil reservation":
            reservations = [body(t) for t in writes if not t["is_error"]]
            reservations = [r for r in reservations if isinstance(r, dict)
                            and isinstance(r.get("reservation"), dict)]
            if not reservations or not any(r.get("created") is True for r in reservations):
                findings.append(f"{name}: no successful new reservation evidence")
            ids = {r["reservation"].get("id") for r in reservations}
            if len(ids) > 1:
                findings.append(f"{name}: more than one reservation ID")
            quote_ids = {c.get("quote_id") for c in checks if c.get("quote_id")}
            for item in reservations:
                reservation = item["reservation"]
                if reservation.get("quote_id") not in quote_ids:
                    findings.append(f"{name}: reservation not grounded in observed quote")
                if any(reservation.get("id", "__absent__") in (turn.get("message") or "")
                       for turn in run["turns"] if turn["role"] == "agent"):
                    findings.append(f"{name}: internal reservation ID spoken without request")
    return findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    findings = audit(json.loads(args.results.read_text()))
    for finding in findings:
        print(finding)
    if findings:
        raise SystemExit(1)
    print("Observable shop checks passed; manual consent, fit and language review still required.")
