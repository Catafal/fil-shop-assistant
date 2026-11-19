"""Authenticated synthetic shop tools and an independently owned browser view."""

import hmac
import re
import sqlite3
import time
from collections.abc import Callable
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from fil_shop.demo import DemoRuntime, DemoSettings, attach_demo, serve_demo_static
from fil_shop.guided import attach_guided
from fil_shop.store import Store, shop_status

CONVERSATION = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
TOOL_KINDS = {"/shop/search": "search", "/shop/check": "check", "/shop/reserve": "reserve"}


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["shirt", "top", "jacket"] | None
    occasion: Literal["wedding", "dinner", "casual"]
    max_price_cents: int = Field(ge=1, le=100000)
    colour: Literal["ivory", "navy", "sage", "terracotta", "black"] | None
    size: Literal["S", "M", "L"] | None


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sku: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=40)
    requested_date: str = Field(min_length=1, max_length=10)
    requested_date_text: str = Field(min_length=1, max_length=300)
    delivery_method: Literal["standard", "express"]


class ReserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    quote_id: str = Field(min_length=1, max_length=80)


class ApiError(Exception):
    def __init__(self, code: str, status: int, payload: dict | None = None):
        self.code, self.status, self.payload = code, status, payload


def create_app(db_path: str | None, webhook_secret: str,
               clock: Callable[[], float] = time.time, *, token_getter: Callable | None = None,
               demo_settings: DemoSettings | None = None,
               store_for_conversation: Callable[[str], Store] | None = None,
               enable_demo: bool = True) -> FastAPI:
    if len(webhook_secret) < 32 or not webhook_secret.isascii():
        raise ValueError("FIL_WEBHOOK_SECRET must be at least 32 ASCII characters")
    if not enable_demo and (token_getter is not None or demo_settings is not None):
        raise ValueError("Tool-only startup cannot configure browser tokens or static/demo settings")
    if store_for_conversation is None:
        if db_path is None:
            raise ValueError("A shared database path or explicit store resolver is required")
        shared_store = Store(db_path, clock)

        def store_for_conversation(conversation: str) -> Store:
            return shared_store

    app = FastAPI(title="Fil synthetic shop", docs_url=None, redoc_url=None, openapi_url=None)
    settings = demo_settings or DemoSettings()
    demo = (attach_demo(app, store_for_conversation, token_getter, settings, clock) if enable_demo
            else DemoRuntime(store_for_conversation, None, settings, clock))

    def authenticated_conversation(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if not hmac.compare_digest(auth.encode(), f"Bearer {webhook_secret}".encode()):
            raise ApiError("webhook_auth_required", 401)
        conversation = request.headers.get("x-conversation-id", "")
        if not CONVERSATION.fullmatch(conversation):
            raise ApiError("invalid_conversation", 400)
        return conversation

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse(exc.payload or {"error": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        kind = TOOL_KINDS.get(request.url.path)
        if kind in ("search", "check"):
            try:
                conversation = authenticated_conversation(request)
                with demo.lock:
                    result = store_for_conversation(conversation).fail(conversation, kind, "invalid_request")
                    demo.observe(conversation, kind, 422, result)
            except (ApiError, sqlite3.Error):
                pass
        return JSONResponse({"error": "invalid_request"}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        return JSONResponse({"error": "backend_unavailable"}, status_code=503)

    async def no_query_selectors(request: Request):
        if request.query_params:
            conversation = authenticated_conversation(request)
            kind = TOOL_KINDS.get(request.url.path)
            with demo.lock:
                result = store_for_conversation(conversation).fail(conversation, kind, "invalid_request")
                demo.observe(conversation, kind, 422, result)
            raise ApiError("invalid_request", 422)

    def outage(conversation: str, kind: str):
        if demo.is_outage(conversation):
            result = store_for_conversation(conversation).fail(conversation, kind, "inventory_unavailable")
            demo.observe(conversation, kind, 503, result)
            raise ApiError("inventory_unavailable", 503, result)

    @app.post("/shop/search", dependencies=[Depends(no_query_selectors)])
    def search(body: SearchRequest, conversation: str = Depends(authenticated_conversation)):
        with demo.lock:
            outage(conversation, "search")
            result = store_for_conversation(conversation).search(conversation, body.model_dump())
            demo.observe(conversation, "search", 200, result)
            return result

    @app.post("/shop/check", dependencies=[Depends(no_query_selectors)])
    def check(body: CheckRequest, conversation: str = Depends(authenticated_conversation)):
        with demo.lock:
            outage(conversation, "check")
            code, result = store_for_conversation(conversation).check(conversation, **body.model_dump())
            demo.observe(conversation, "check", shop_status(code), result)
            if code != "ok":
                raise ApiError(code, shop_status(code), result)
            return result

    @app.post("/shop/reserve", dependencies=[Depends(no_query_selectors)])
    def reserve(body: ReserveRequest, conversation: str = Depends(authenticated_conversation)):
        with demo.lock:
            outage(conversation, "reserve")
            code, result = store_for_conversation(conversation).reserve(conversation, body.quote_id)
            demo.observe(conversation, "reserve", shop_status(code), result)
            if code != "ok":
                raise ApiError(code, shop_status(code), result)
            return result

    if enable_demo:
        attach_guided(app, demo)
        serve_demo_static(app, settings.static_dir)
    return app
