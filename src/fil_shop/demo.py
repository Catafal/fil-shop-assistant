"""Ephemeral browser ownership and safe observations of real shop webhook results."""

import hmac
import ipaddress
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from elevenlabs.core.api_error import ApiError as ProviderApiError
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from httpx import HTTPError
from pydantic import BaseModel, ConfigDict

from fil_shop.store import Store, shop_status

SESSION_SECONDS = 30 * 60
COOKIE = "fil_demo_owner"
OWNER = re.compile(r"[a-f0-9]{64}\Z")
DEFAULT_ORIGINS = (
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:5173", "http://127.0.0.1:5173",
)
SCENARIOS = [
    {"id": "normal", "label": "Compra amb Ona"},
    {"id": "inventory-outage", "label": "Inventari no disponible"},
]


@dataclass(frozen=True)
class DemoSettings:
    access_code: str = ""
    origins: tuple[str, ...] = DEFAULT_ORIGINS
    secure_cookies: bool = False
    static_dir: str | None = None


@dataclass
class DemoSession:
    id: str
    owner: str
    conversation_id: str
    scenario: str
    created_at: float
    expires_at: float
    status: str = "active"
    reservation_quote: str | None = None
    last_retry: dict | None = None
    events: list[dict] = field(default_factory=list)

    def record(self, kind: str, status: int, payload: dict, now: float):
        self.events.append({"sequence": len(self.events) + 1, "at": now,
                            "kind": kind, "status": status, "payload": payload})

    def snapshot(self, store: Store) -> dict:
        projection = store.projection(self.conversation_id)
        reservation = projection["reservation"]
        retry = (self.last_retry if reservation and reservation["status"] == "active"
                 and self.last_retry
                 and self.last_retry["reservation"]["id"] == reservation["id"] else None)
        return {"session": {k: getattr(self, k) for k in
                            ("id", "scenario", "status", "created_at", "expires_at",
                             "conversation_id")}, **projection,
                "events": list(self.events), "last_retry": retry}


class DemoError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status


class DemoRuntime:
    def __init__(self, store_for_conversation: Callable[[str], Store], token_getter: Callable | None,
                 settings: DemoSettings, clock: Callable[[], float] = time.time):
        self.store_for_conversation = store_for_conversation
        self.token_getter, self.settings, self.clock = token_getter, settings, clock
        self.lock = threading.RLock()
        self.sessions: dict[str, DemoSession] = {}
        self.conversations: dict[str, DemoSession] = {}
        self.gates: dict[str, float] = {}
        self.rate_windows: dict[str, deque] = defaultdict(deque)
        if any(origin in ("*", "null", "") for origin in settings.origins):
            raise ValueError("Demo origins must be explicit origins")

    def local(self, request: Request) -> bool:
        # A public tunnel may connect from loopback. Host AND peer must be local,
        # and proxy markers must not be silently treated as a local browser.
        if any(k == "forwarded" or k.startswith(("x-forwarded-", "cf-"))
               for k in request.headers):
            return False
        try:
            peer_local = bool(request.client and ipaddress.ip_address(request.client.host).is_loopback)
        except ValueError:
            peer_local = False
        return peer_local and request.url.hostname in ("localhost", "127.0.0.1", "::1")

    def owner(self, request: Request) -> str:
        value = request.cookies.get(COOKIE, "")
        if not OWNER.fullmatch(value):
            raise DemoError("session_required", 403)
        return value

    def hosting(self, request: Request):
        if not self.settings.access_code and not self.local(request):
            raise DemoError("local_access_only", 403)
        if self.settings.access_code and not self.local(request) and not self.settings.secure_cookies:
            raise DemoError("secure_cookie_required", 503)

    def access(self, request: Request) -> str:
        self.hosting(request)
        owner = self.owner(request)
        if request.query_params:
            raise DemoError("invalid_request", 422)
        if self.settings.access_code and self.gates.get(owner, 0) <= self.clock():
            raise DemoError("access_required", 403)
        return owner

    def mutation(self, request: Request) -> str:
        if request.headers.get("origin") not in self.settings.origins:
            raise DemoError("origin_denied", 403)
        return self.access(request)

    def rate(self, limits: list[tuple[str, int, int]]):
        now = self.clock()
        for key, count, seconds in limits:
            window = self.rate_windows[key]
            while window and window[0] <= now - seconds:
                window.popleft()
            if len(window) >= count:
                raise DemoError("rate_limited", 429)
        for key, _, _ in limits:
            self.rate_windows[key].append(now)

    def grant(self, request: Request, code: str):
        if request.headers.get("origin") not in self.settings.origins:
            raise DemoError("origin_denied", 403)
        self.hosting(request)
        owner = self.owner(request)
        peer = request.client.host if request.client else "unknown"
        with self.lock:
            self.rate([("access:" + peer, 5, 60), ("access:global", 30, 60)])
            if not self.settings.access_code or not hmac.compare_digest(
                code.encode(), self.settings.access_code.encode()
            ):
                raise DemoError("access_denied", 403)
            self.gates[owner] = self.clock() + SESSION_SECONDS
        return {"granted": True}

    def start(self, request: Request, scenario: str, owner: str) -> dict:
        peer = request.client.host if request.client else "unknown"
        with self.lock:
            previous = self.sessions.get(owner)
            if previous and previous.status == "active" and previous.expires_at > self.clock():
                raise DemoError("session_active", 409)
            if self.token_getter is None:
                raise DemoError("not_configured", 503)
            # Reserve before the external call. Failed/uncertain minting consumes this allowance.
            self.rate([("tokens:owner:" + owner, 5, 3600),
                       ("tokens:peer:" + peer, 10, 3600), ("tokens:global", 20, 3600)])
            try:
                result = self.token_getter()
                token = result.get("token") if isinstance(result, dict) else result.token
                conversation = (result.get("conversation_id") if isinstance(result, dict)
                                else result.conversation_id)
                if (not isinstance(token, str) or not token or not isinstance(conversation, str)
                        or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", conversation)
                        or conversation in self.conversations):
                    raise ValueError("Invalid provider response")
            except (ProviderApiError, HTTPError, ValueError, TypeError, AttributeError,
                    RuntimeError, OSError):
                # Provider errors may include capabilities or request credentials; never echo them.
                raise DemoError("provider_unavailable", 503) from None
            now = self.clock()
            session = DemoSession(secrets.token_hex(16), owner, conversation, scenario,
                                  now, now + SESSION_SECONDS)
            self.sessions[owner] = session
            self.conversations[conversation] = session
            return {"id": session.id, "conversation_token": token,
                    "conversation_id": conversation, "expires_at": session.expires_at}

    def current(self, owner: str) -> DemoSession | None:
        session = self.sessions.get(owner)
        if session and session.expires_at <= self.clock():
            raise DemoError("session_expired", 410)
        return session

    def live(self, conversation: str) -> DemoSession | None:
        session = self.conversations.get(conversation)
        if session and session.status == "active" and session.expires_at > self.clock():
            return session
        return None

    def is_outage(self, conversation: str) -> bool:
        with self.lock:
            session = self.live(conversation)
            return bool(session and session.scenario == "inventory-outage")

    def observe(self, conversation: str, kind: str, status: int, payload: dict):
        with self.lock:
            session = self.live(conversation)
            if session is None:
                return
            # Only our structured shop responses enter history; never raw request bodies/headers.
            safe = dict(payload)
            if kind == "reserve" and status == 200:
                session.reservation_quote = payload["reservation"]["quote_id"]
                if (session.last_retry and session.last_retry["reservation"]["id"]
                        != payload["reservation"]["id"]):
                    session.last_retry = None
            session.record(kind, status, safe, self.clock())

    def snapshot(self, owner: str) -> dict:
        with self.lock:
            session = self.current(owner)
            empty = {"session": None, "revision": 0, "criteria": None, "products": [],
                     "checked": None, "quote": None, "reservation": None, "error": None,
                     "events": [], "last_retry": None}
            if session is None:
                return empty
            # Current state comes from one authoritative SQLite snapshot, never late callbacks.
            return session.snapshot(self.store_for_conversation(session.conversation_id))

    def retry(self, owner: str) -> dict:
        with self.lock:
            session = self.current(owner)
            if not session or session.status != "active" or not session.reservation_quote:
                raise DemoError("retry_unavailable", 409)
            code, result = self.store_for_conversation(session.conversation_id).reserve(
                session.conversation_id, session.reservation_quote, existing_only=True,
            )
            status = shop_status(code)
            session.record("operator_retry", status, result, self.clock())
            if code != "ok":
                raise DemoError(code, status)
            session.last_retry = dict(result)
            return result

    def end(self, owner: str) -> dict:
        with self.lock:
            session = self.current(owner)
            if session:
                session.status = "ended"
            return {"ended": True}


class AccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    code: str


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario: Literal["normal", "inventory-outage"]


def attach_demo(app: FastAPI, store_for_conversation: Callable[[str], Store],
                token_getter: Callable | None,
                settings: DemoSettings, clock: Callable[[], float]) -> DemoRuntime:
    runtime = DemoRuntime(store_for_conversation, token_getter, settings, clock)

    @app.exception_handler(DemoError)
    async def demo_error(request: Request, exc: DemoError):
        return JSONResponse({"error": exc.code}, status_code=exc.status,
                            headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def no_demo_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/demo/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/demo/config")
    def config(request: Request, response: Response):
        runtime.hosting(request)
        owner = request.cookies.get(COOKIE, "")
        if not OWNER.fullmatch(owner):
            owner = secrets.token_hex(32)
        response.set_cookie(COOKIE, owner, httponly=True, secure=settings.secure_cookies,
                            samesite="strict", path="/demo", max_age=SESSION_SECONDS)
        return {"configured": token_getter is not None,
                "access_required": bool(settings.access_code
                                        and runtime.gates.get(owner, 0) <= clock()),
                "brand": "Fil",
                "scenarios": SCENARIOS}

    @app.post("/demo/access")
    def access(body: AccessRequest, request: Request):
        return runtime.grant(request, body.code)

    @app.post("/demo/sessions")
    def start(body: SessionRequest, request: Request, owner: str = Depends(runtime.mutation)):
        return runtime.start(request, body.scenario, owner)

    @app.get("/demo/session")
    def snapshot(owner: str = Depends(runtime.access)):
        return runtime.snapshot(owner)

    async def no_control_body(request: Request):
        if request.query_params or await request.body():
            raise DemoError("invalid_request", 422)

    @app.post("/demo/session/retry", dependencies=[Depends(no_control_body)])
    def retry(owner: str = Depends(runtime.mutation)):
        return runtime.retry(owner)

    @app.post("/demo/session/end", dependencies=[Depends(no_control_body)])
    def end(owner: str = Depends(runtime.mutation)):
        return runtime.end(owner)

    return runtime


def serve_demo_static(app: FastAPI, directory: str | None):
    if directory is None or not (Path(directory) / "index.html").is_file():
        return
    root = Path(directory).resolve()

    @app.get("/{path:path}")
    def static(path: str):
        if path.split("/", 1)[0] in ("demo", "shop", "verify", "usage", "billing", "tickets"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            return JSONResponse({"error": "not_found"}, status_code=404)
        if target.is_file():
            return FileResponse(target)
        return FileResponse(root / "index.html")
