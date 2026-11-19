"""A fixed browser exercise with one disposable inventory per session."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field

from fil_shop.demo import SESSION_SECONDS, DemoError, DemoRuntime, DemoSession
from fil_shop.store import ZONE, Store, shop_status

MAX_SESSIONS = 32
CRITERIA = {"occasion": "wedding", "category": "shirt", "max_price_cents": 12000,
            "size": "M", "colour": "navy"}
SKU = "FIL02-M-SAGE"
Stage = Literal["initial", "revised", "quoted", "held", "declined", "outage"]
Action = Literal["change-colour", "check", "reserve", "decline", "retry"]


class GuidedStart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario: Literal["normal", "inventory-outage"]
    restart_from: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class GuidedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    action: Action


@dataclass
class GuidedSession:
    session: DemoSession
    directory: TemporaryDirectory
    store: Store
    stage: Stage

    def snapshot(self) -> dict:
        return {"stage": self.stage, "view": self.session.snapshot(self.store)}

    def act(self, action: Action, now: float):
        session, store = self.session, self.store
        conversation = session.conversation_id
        code = "ok"
        if action == "change-colour" and self.stage == "initial":
            payload = store.search(conversation, {**CRITERIA, "colour": "sage"})
            self.stage = "revised"
            kind = "search"
        elif action == "check" and self.stage in ("revised", "quoted"):
            if self.stage == "quoted" and store.projection(conversation)["quote"]:
                return
            deadline = (datetime.fromtimestamp(now, ZONE).date() + timedelta(days=7)).isoformat()
            code, payload = store.check(conversation, SKU, "Barcelona", deadline, "standard",
                                        requested_date_text=deadline)
            if code == "ok":
                self.stage = "quoted"
                session.reservation_quote = payload["quote_id"]
            kind = "check"
        elif action == "reserve" and self.stage == "quoted" and session.reservation_quote:
            code, payload = store.reserve(conversation, session.reservation_quote)
            if code == "ok":
                self.stage = "held"
            kind = "reserve"
        elif action == "decline" and self.stage == "quoted":
            self.stage = "declined"
            kind, payload = "decline", {}
        elif action == "retry" and self.stage == "held" and session.reservation_quote:
            code, payload = store.reserve(conversation, session.reservation_quote, existing_only=True)
            if code == "ok":
                if session.last_retry is not None:
                    return
                session.last_retry = payload
            kind = "operator_retry"
        elif (action, self.stage) in {("change-colour", "revised"), ("reserve", "held"),
                                      ("decline", "declined")}:
            return
        else:
            raise DemoError("guided_step_unavailable", 409)
        status = shop_status(code)
        if code != "ok":
            raise DemoError(code, status)
        session.record(kind, status, payload, now)


def attach_guided(app: FastAPI, demo: DemoRuntime):
    sessions: dict[str, GuidedSession] = {}

    def prune():
        now = demo.clock()
        for owner, guided in list(sessions.items()):
            if guided.session.expires_at <= now:
                guided.directory.cleanup()
                del sessions[owner]

    @app.get("/demo/guided")
    def guided_snapshot(owner: str = Depends(demo.access)):
        with demo.lock:
            prune()
            guided = sessions.get(owner)
            return guided.snapshot() if guided else None

    @app.post("/demo/guided")
    def guided_start(body: GuidedStart, request: Request, owner: str = Depends(demo.mutation)):
        with demo.lock:
            prune()
            previous = sessions.get(owner)
            if previous and body.restart_from != previous.session.id:
                return previous.snapshot()
            if not previous and len(sessions) >= MAX_SESSIONS:
                raise DemoError("rate_limited", 429)
            peer = request.client.host if request.client else "unknown"
            demo.rate([("guided:owner:" + owner, 12, 60), ("guided:peer:" + peer, 32, 60),
                       ("guided:global", 64, 60)])
            now = demo.clock()
            identifier = secrets.token_hex(16)
            session = DemoSession(identifier, owner, f"guided-{identifier}", body.scenario,
                                  now, now + SESSION_SECONDS)
            directory = TemporaryDirectory(prefix="fil-guided-")
            store = Store(Path(directory.name) / "fil.sqlite", demo.clock)
            if body.scenario == "inventory-outage":
                payload = store.fail(session.conversation_id, "search", "inventory_unavailable")
                session.record("search", 503, payload, now)
                guided = GuidedSession(session, directory, store, "outage")
            else:
                payload = store.search(session.conversation_id, CRITERIA)
                session.record("search", 200, payload, now)
                guided = GuidedSession(session, directory, store, "initial")
            sessions[owner] = guided
            if previous:
                previous.directory.cleanup()
            return guided.snapshot()

    @app.post("/demo/guided/action")
    def guided_action(body: GuidedAction, owner: str = Depends(demo.mutation)):
        with demo.lock:
            prune()
            guided = sessions.get(owner)
            if guided is None:
                raise DemoError("session_expired", 410)
            if body.id != guided.session.id:
                raise DemoError("guided_step_unavailable", 409)
            guided.act(body.action, demo.clock())
            return guided.snapshot()
