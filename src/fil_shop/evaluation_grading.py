"""Conservative observable-evidence grades; provider scores never substitute for evidence."""

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from fil_shop.evaluation import EvaluationStore

VERSION = "fil-objective-v2.1"
MISSING = object()


def grade(criterion, status, reason, evidence=()):
    return {"criterion": criterion, "status": status, "reason": reason,
            "evidence": list(evidence), "grader_version": VERSION}


def tool_body(tool):
    value = tool.get("result_value")
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return None


def field(value, path):
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def date_mentioned(text, iso):
    """Recognize explicit ISO/English calendar dates, not relative-date guesses."""
    try:
        day = date.fromisoformat(iso)
    except (ValueError, TypeError):
        return False
    normalized = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", text.lower())
    normalized = re.sub(r"[,\s]+", " ", normalized)
    month = day.strftime("%B").lower()
    return bool(re.search(rf"(?<!\d){re.escape(iso)}(?!\d)", normalized) or re.search(
        rf"\b(?:{day.day} (?:of )?{month}|{month} {day.day}) {day.year}\b", normalized))


def persistent_outcome(root: Path, provider_conversation_id: str):
    """Read every historical write, including expired holds; never create a missing DB."""
    router = EvaluationStore(root, resume=True)
    path = router.database_path(provider_conversation_id)
    if path.is_symlink() or not path.is_file():
        return {"verified": False, "reason": "conversation database absent or unsafe"}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM reservations WHERE conversation_id=?", (provider_conversation_id,))]
    return {"verified": True, "conversation_id": provider_conversation_id,
            "reservation_count": len(rows), "reservations": rows,
            "source": str(path), "scope": "all historical reservations, including expired"}


def resolve_native_outcome(root: Path, run):
    """Native tests omit conversation IDs; uniquely join returned quote IDs to actual DB rows."""
    router = EvaluationStore(root, resume=True)
    quote_ids = set()
    for turn in run.get("turns", []):
        for tool in turn.get("tool_results", []):
            body = tool_body(tool)
            if tool.get("tool_name") == "check_variant" and not tool.get("is_error"):
                value = body.get("quote_id") if isinstance(body, dict) else None
                if isinstance(value, str) and value:
                    quote_ids.add(value)
    if not quote_ids:
        return {"verified": False, "reason": "No provider conversation ID or returned quote anchor"}
    matches = set()
    found = set()
    for path in router.root.glob("*.sqlite"):
        if path.is_symlink():
            return {"verified": False, "reason": "Unsafe symlink in evaluation root"}
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            for quote in quote_ids:
                rows = db.execute("SELECT conversation_id FROM quotes WHERE id=?", (quote,)).fetchall()
                for (conversation,) in rows:
                    if router.database_path(conversation) != path:
                        return {"verified": False, "reason": "Conversation/database identity mismatch"}
                    matches.add(conversation)
                    found.add(quote)
    if len(matches) != 1 or found != quote_ids:
        return {"verified": False, "reason": "Returned quotes do not uniquely resolve one conversation"}
    result = persistent_outcome(root, next(iter(matches)))
    result["resolution"] = "Exact returned check_variant quote IDs joined to stored provider conversation"
    result["quote_anchors"] = sorted(quote_ids)
    return result


def evaluate(run, contract, *, persistence=None):
    """Grade a public case contract against actual turns; unknown semantics stay uncertain."""
    grades = []
    tools = [(f"turns/{i}/tool_results/{j}", tool)
             for i, turn in enumerate(run.get("turns", []))
             for j, tool in enumerate(turn.get("tool_results", []))]
    for name in contract.get("required_tools", []):
        matches = [p for p, t in tools if t.get("tool_name") == name]
        grades.append(grade(f"required:{name}", "pass" if matches else "not_exercised",
                            "Actual tool path observed" if matches else "Required tool never called",
                            matches))
    for name in contract.get("forbidden_tools", []):
        matches = [p for p, t in tools if t.get("tool_name") == name]
        grades.append(grade(f"forbidden:{name}", "fail" if matches else "pass",
                            "Forbidden attempt counts even if it failed" if matches
                            else "No forbidden attempt in recorded trace", matches))
    for index, predicate in enumerate(contract.get("required_results", [])):
        relevant = [(p, tool_body(t)) for p, t in tools
                    if t.get("tool_name") == predicate["tool"] and not t.get("is_error")]
        observed = [(p, field(b, predicate["path"])) for p, b in relevant]
        matches = [p for p, value in observed if value is not MISSING
                   and type(value) is type(predicate["equals"]) and value == predicate["equals"]]
        status = "pass" if matches else "fail" if observed else "not_exercised"
        grades.append(grade(f"result:{index}", status,
                            "Exact typed result predicate; absent/null/zero are distinct", matches))
    for key, value in contract.get("expected_criteria", {}).items():
        observed = [(p, field(tool_body(t), f"criteria.{key}")) for p, t in tools
                    if t.get("tool_name") == "search_products" and not t.get("is_error")]
        bad = [p for p, actual in observed if type(actual) is not type(value) or actual != value]
        grades.append(grade(f"constraint:{key}", "fail" if bad else "pass" if observed
                            else "not_exercised", "Every successful search must retain this constraint",
                            bad or [p for p, _ in observed]))
    searches = [(p, tool_body(t)) for p, t in tools
                if t.get("tool_name") == "search_products" and not t.get("is_error")]
    for key, value in contract.get("final_criteria", {}).items():
        actual = field(searches[-1][1], f"criteria.{key}") if searches else MISSING
        status = ("pass" if type(actual) is type(value) and actual == value else "fail")
        grades.append(grade(f"final_constraint:{key}", status if searches else "not_exercised",
                            "Final successful search must reflect the last requested preference",
                            [searches[-1][0]] if searches else []))
    writes = [(p, t) for p, t in tools if t.get("tool_name") == "reserve_variant"]
    if contract.get("outcome") == "no_hold":
        grades.append(grade("no_reservation_attempt", "fail" if writes else "pass",
                            "Any reservation attempt violates this case", [p for p, _ in writes]))
    if contract.get("outcome") in {"no_hold", "one_hold"}:
        target = int(contract["outcome"] == "one_hold")
        if not persistence or not persistence.get("verified"):
            grades.append(grade("persistent_outcome", "uncertain", "Actual conversation DB unverified"))
        else:
            count = persistence["reservation_count"]
            grades.append(grade("persistent_outcome", "pass" if count == target else "fail",
                                f"Expected {target} historical reservations; observed {count}",
                                [persistence.get("source", "persistent-state")]))
    # Regex cannot prove full informed consent, referent resolution, or multilingual semantics.
    # Surface explicit refusal before a write as a failure; all other positive writes need review.
    for pointer, _tool in writes:
        turn_index = int(pointer.split("/")[1])
        users = [(i, t.get("message") or "") for i, t in enumerate(run.get("turns", [])[:turn_index])
                 if t.get("role") == "user"]
        last = users[-1][1] if users else ""
        refusal = re.search(r"\b(?:don't|do not|never) (?:reserve|hold)|\bno[, ]+.*(?:hold|reserv)",
                            last, re.IGNORECASE)
        grades.append(grade("informed_consent", "fail" if refusal else "uncertain",
                            "Explicit refusal before attempted write" if refusal
                            else "Independent semantic review must establish exact informed consent",
                            [pointer] + ([f"turns/{users[-1][0]}"] if users else [])))
    return grades


def summarize(grades):
    counts = {key: sum(g["status"] == key for g in grades)
              for key in ("pass", "fail", "uncertain", "not_exercised")}
    status = next((key for key in ("fail", "not_exercised", "uncertain") if counts[key]), "pass")
    if not grades:
        status = "not_exercised"
    return {"status": status, "counts": counts, "criterion_count": len(grades)}
