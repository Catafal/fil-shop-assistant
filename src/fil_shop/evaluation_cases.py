"""Freeze calendar-valid evaluation inputs once, shared by compared models."""
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def materialize_cases(cases: list[dict], now: datetime | None = None) -> tuple[list[dict], dict]:
    local = (now or datetime.now(ZoneInfo("Europe/Madrid"))).astimezone(ZoneInfo("Europe/Madrid"))
    deadline = local.date() + timedelta(days=14)
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    values = {"deadline": deadline.isoformat(), "weekday": weekdays[deadline.weekday()],
              "wrong_weekday": weekdays[(deadline.weekday() + 1) % 7]}
    text = json.dumps(cases, ensure_ascii=False)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    resolved = json.loads(text)
    if unresolved_template(resolved):
        raise ValueError("Unresolved evaluation fixture placeholder")
    return resolved, {**values, "materialized_at": local.isoformat(),
                              "timezone": "Europe/Madrid"}


def validate_fixture(fixture: dict, source_digest: str) -> dict:
    if fixture.get("source_sha256") != source_digest:
        raise ValueError("Fixture belongs to a different scenario source")
    actual = hashlib.sha256(json.dumps(fixture["cases"], sort_keys=True).encode()).hexdigest()
    if fixture.get("materialized_sha256") != actual:
        raise ValueError("Frozen case artifact was changed")
    if unresolved_template(fixture["cases"]):
        raise ValueError("Frozen fixture contains unresolved dates")
    return fixture


def unresolved_template(value):
    """Check string values/keys, not structural adjacent JSON braces in metadata."""
    if isinstance(value, str):
        return "{{" in value or "}}" in value
    if isinstance(value, dict):
        return any(unresolved_template(k) or unresolved_template(v) for k, v in value.items())
    if isinstance(value, list):
        return any(unresolved_template(item) for item in value)
    return False
