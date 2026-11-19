"""Pure audio-evaluation contracts; no provider calls or physical-playback claims."""
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fil_shop.evaluation import CONVERSATION, MARKER, ROOT_IDENTITY

HARNESS_VERSION = "fil-audio-v2.1"
KINDS = {"request", "language_switch", "user_interruption", "goodbye"}
# Backchannel/background/sentence-pause traces may be recorded, but runnable cases
# need an explicit no-response policy before those stimuli can be graded safely.


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def provider_digest(snapshot, kind):
    keys = ("agent_id", "conversation_config", "platform_settings", "workflow") if kind == "agent" else ("id", "tool_config")
    return digest({key: snapshot.get(key) for key in keys})


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_case(path):
    case = json.loads(Path(path).read_text())
    if not isinstance(case.get("id"), str) or not case["id"] or case.get("version") != 1:
        raise ValueError("Versioned audio case ID/version required")
    if not 30 <= case.get("max_seconds", 0) <= 240:
        raise ValueError("Audio case requires a 30..240 second cap")
    turns = case.get("turns", [])
    if not 1 <= len(turns) <= 12 or len({t.get("id") for t in turns}) != len(turns):
        raise ValueError("Audio case needs 1..12 uniquely identified turns")
    for index, turn in enumerate(turns):
        if (not isinstance(turn.get("id"), str) or not turn["id"]
                or turn.get("language") not in {"en", "ca", "es"}
                or turn.get("kind") not in KINDS
                or turn.get("send_mode") not in {"after_response", "overlap"}
                or not isinstance(turn.get("text"), str) or not 1 <= len(turn["text"]) <= 700):
            raise ValueError("Invalid audio turn contract")
        patterns = turn.get("required_asr_patterns", [])
        if not patterns or not all(isinstance(p, str) and 0 < len(p) <= 200 for p in patterns):
            raise ValueError("Every audio turn requires explicit ASR coverage patterns")
        for pattern in patterns:
            re.compile(pattern, re.IGNORECASE)
        if index == 0 and turn["send_mode"] != "after_response":
            raise ValueError("First turn must follow greeting")
    patterns = case.get("final_required_spoken_patterns")
    if not patterns or not all(isinstance(p, str) and len(p) <= 200 for p in patterns):
        raise ValueError("Explicit final spoken-content patterns required")
    for pattern in patterns:
        re.compile(pattern, re.IGNORECASE)
    return case


def validate_case_clock(case, today=None):
    if "date_window" not in case:
        return
    today = today or datetime.now(ZoneInfo("Europe/Madrid")).date()
    window = case["date_window"]
    deadline, last_start = date.fromisoformat(window["deadline"]), date.fromisoformat(window["last_start_date"])
    if last_start >= deadline or today > last_start:
        raise ValueError("Frozen audio dates expired; author a new case version, do not silently rematerialize")


def trial_validity(transport, spoken):
    if transport["status"] != "completed":
        return "incomplete"
    return {"pass": "audio_content_present_semantics_pending", "fail": "required_spoken_content_failed"}.get(
        spoken["status"], "awaiting_spoken_content_review")


def validate_target(manifest, agent_id, root, live_agent_id):
    """Operator provision manifest is a trust boundary, never a model-selected target."""
    root = Path(root)
    if not live_agent_id:
        raise ValueError("Set ELEVENLABS_AGENT_ID to the live agent before running an evaluation")
    if agent_id == live_agent_id:
        raise ValueError("Live agent is forbidden for evaluation")
    if (manifest.get("schema") != 1 or manifest.get("purpose") != "fil-audio-evaluation"
            or manifest.get("agent_id") != agent_id
            or Path(manifest.get("evaluation_root", "")).resolve() != root.resolve()):
        raise ValueError("Evaluation target differs from provisioned manifest")
    marker = root / MARKER
    if root.is_symlink() or marker.is_symlink() or not marker.is_file():
        raise ValueError("Explicit marked evaluation root required")
    if json.loads(marker.read_text()) != ROOT_IDENTITY:
        raise ValueError("Invalid evaluation root marker")
    ids = manifest.get("tool_ids", {})
    if len(set(ids.values())) != 3 or any(not isinstance(v, str) or not v for v in ids.values()):
        raise ValueError("Distinct evaluation tool IDs required")
    if set(ids) != {"search_products", "check_variant", "reserve_variant"}:
        raise ValueError("Three isolated evaluation tool IDs required")
    hashes = manifest.get("tool_snapshot_sha256", {})
    if set(hashes) != set(ids) or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("agent_snapshot_sha256", "")):
        raise ValueError("Provider snapshot hashes required")
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(v)) for v in hashes.values()):
        raise ValueError("Invalid tool snapshot digest")
    return root.resolve()


def database_path(root, conversation_id):
    if not CONVERSATION.fullmatch(conversation_id):
        raise ValueError("Invalid provider conversation ID")
    path = Path(root) / (hashlib.sha256(conversation_id.encode()).hexdigest() + ".sqlite")
    if path.is_symlink():
        raise ValueError("Evaluation database symlink forbidden")
    return path


def read_outcome(root, conversation_id):
    path = database_path(root, conversation_id)
    if not path.exists():
        return {"status": "not_exercised", "reason": "No isolated tool database exists"}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        context = db.execute("SELECT criteria,checked,error FROM shopping_contexts "
                             "WHERE conversation_id=?", (conversation_id,)).fetchone()
        rows = db.execute("SELECT id,quote_id,sku,created_at,expires_at FROM reservations "
                          "WHERE conversation_id=?", (conversation_id,)).fetchall()
    return {"status": "observed", "database_file": path.name,
            "criteria": json.loads(context[0]) if context and context[0] else None,
            "checked": json.loads(context[1]) if context and context[1] else None,
            "error": context[2] if context else None,
            "reservations": [dict(zip(("id", "quote_id", "sku", "created_at", "expires_at"), row))
                             for row in rows]}


def response_follows_input(input_started, user_at, agent_at, audio_at):
    return user_at >= input_started and agent_at > user_at and audio_at >= agent_at


@dataclass
class AudioTrace:
    """Observed event chronology, independent of wall clock/network for trace regressions."""
    input_at: float = -1
    input_id: str | None = None
    user_at: float = -1
    agent_at: float = -1
    audio_at: float = -1
    interruption_at: float = -1
    last_interrupt_id: int = -1
    playback_until: float = 0
    received_bytes: int = 0
    discarded_bytes: int = 0
    response_generation: int = 0
    response_id: str | None = None
    response_event_id: int | None = None
    current_asr: list = field(default_factory=list)
    end: dict | None = None
    errors: list = field(default_factory=list)
    events: list = field(default_factory=list)

    def observe(self, kind, at, **data):
        if self.events and at < self.events[-1]["at"]:
            raise ValueError("Audio events must use monotonic timestamps")
        event = {"type": kind, "at": at, **data}
        if kind == "input_start":
            self.input_at, self.input_id = at, data["id"]
            self.current_asr = []
        elif kind == "user_transcript":
            self.user_at = at
            self.current_asr.append(data.get("text", ""))
        elif kind == "agent_response":
            self.agent_at = at
            self.response_generation += 1
            self.response_id, self.response_event_id = data.get("response_id"), data.get("event_id")
        elif kind == "audio":
            size, rate, event_id = data["bytes"], data["rate"], data["event_id"]
            if size <= 0 or size % 2 or rate <= 0:
                raise ValueError("Invalid PCM chunk")
            event["response_generation"] = self.response_generation
            if self.response_id is not None and data.get("response_id") is not None:
                event["association"] = "explicit" if self.response_id == data["response_id"] else "mismatch"
            elif self.response_event_id is not None:
                event["association"] = "turn_id_only" if self.response_event_id == event_id else "mismatch"
            else:
                event["association"] = "temporal_only"
            event["discarded"] = event_id <= self.last_interrupt_id
            if event["discarded"]:
                self.discarded_bytes += size
            else:
                event["stream_offset"] = self.received_bytes
                self.received_bytes += size
                if event["association"] != "mismatch":
                    self.audio_at = at
                self.playback_until = max(at, self.playback_until) + size / (2 * rate)
        elif kind == "interruption":
            self.interruption_at = at
            self.last_interrupt_id = max(self.last_interrupt_id, data["event_id"])
            self.playback_until = at
        elif kind == "provider_end":
            self.end = {"at": at, "code": data.get("code"), "reason": data.get("reason")}
        elif kind in {"timeout", "tool_error", "provider_error", "harness_error"}:
            self.errors.append({"type": kind, "at": at, "code": data.get("code")})
        self.events.append(event)
        return event

    def input_covered(self, patterns):
        text = " ".join(self.current_asr)
        return all(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    def response_ordered(self):
        return (response_follows_input(self.input_at, self.user_at, self.agent_at, self.audio_at)
                and self.agent_at > self.interruption_at)

    def drained(self, now):
        return self.response_ordered() and now >= max(self.playback_until, self.audio_at) + .8

    def greeting_ready(self, now):
        return self.agent_at >= 0 and self.audio_at >= self.agent_at and now >= self.playback_until + .8

    def transport_verdict(self, now, all_sent, *, input_covered=True):
        if any(e["type"] in {"timeout", "harness_error"} for e in self.errors):
            return {"status": "incomplete", "reason": "harness_timeout_or_error"}
        if any(e["type"] == "provider_error" for e in self.errors):
            return {"status": "incomplete", "reason": "provider_error"}
        if not all_sent or not self.response_ordered():
            return {"status": "incomplete", "reason": "final_response_absent_or_interrupted"}
        if not input_covered:
            return {"status": "incomplete", "reason": "caller_input_not_fully_recognized"}
        if self.end and self.end.get("code") not in (1000, 1001):
            return {"status": "incomplete", "reason": "abnormal_provider_end"}
        if not self.drained(now):
            return {"status": "incomplete", "reason": "audio_not_drained"}
        return {"status": "completed", "reason": "ordered_response_and_received_audio_drained"}


def spoken_grade(case, audio_path, evidence=None, association="unverified"):
    if evidence is None:
        return {"status": "uncertain", "reason": "Independent final-audio content evidence required"}
    if (evidence.get("audio_sha256") != file_digest(audio_path)
            or not evidence.get("transcriber_version") or not isinstance(evidence.get("text"), str)):
        raise ValueError("Spoken evidence must identify the exact final audio artifact and transcriber")
    missing = [p for p in case["final_required_spoken_patterns"]
               if not re.search(p, evidence["text"], re.IGNORECASE)]
    return {"status": ("fail" if missing else "pass") if association == "explicit" else "uncertain",
            "content_match": not missing, "audio_association": association, "missing_patterns": missing,
            "criterion": "required_content_presence_only", "semantic_acceptance": "uncertain",
            "method": "versioned_required_content_patterns_on_independent_STT",
            "limits": "Does not certify human naturalness or physical playback"}


def business_state_grade(case, outcome, events):
    """Grade observed state; incomplete streaming traces cannot prove absent actions/consent."""
    if outcome.get("status") != "observed":
        return {"status": "uncertain", "criteria": [], "reason": "Persistent outcome unavailable"}
    expected = case.get("expected_state", {})
    checks = []
    current = outcome.get("criteria") or {}
    rows = outcome.get("reservations", [])
    for key, wanted in expected.items():
        if key in {"colour", "size", "max_price_cents", "occasion", "category"}:
            observed = current.get(key)
        elif key == "reservations":
            observed = len(rows)
        elif key == "sku":
            observed = rows[0].get("sku") if len(rows) == 1 else None
        elif key == "required_tool_error":
            observed = outcome.get("error")
        else:
            checks.append({"criterion": key, "status": "uncertain", "reason": "Unsupported state criterion"})
            continue
        checks.append({"criterion": key, "status": "pass" if observed == wanted else "fail",
                       "expected": wanted, "observed": observed, "evidence": "persistent_outcome"})
    attempts = [index for index, event in enumerate(events)
                if event.get("tool_name") == "reserve_variant"]
    if expected.get("reservations") == 0:
        checks.append({"criterion": "no_transient_reservation_attempt", "status": "fail" if attempts else "uncertain",
                       "evidence_events": attempts,
                       "reason": "Observed reserve attempt" if attempts else "Streaming trace completeness not established"})
    elif expected.get("reservations", 0) > 0:
        checks.append({"criterion": "explicit_consent_before_reservation", "status": "uncertain",
                       "reason": "Requires independent complete transcript/tool-order semantic review"})
    statuses = {item["status"] for item in checks}
    status = "fail" if "fail" in statuses else "uncertain" if not checks or "uncertain" in statuses else "pass"
    return {"status": status, "criteria": checks, "semantic_acceptance": "uncertain",
            "limits": "State success and content presence never alone establish case acceptance"}
