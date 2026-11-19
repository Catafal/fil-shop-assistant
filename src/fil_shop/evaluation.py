"""Explicit evaluation-only inventory routing; production startup never imports this module."""

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from fil_shop.api import create_app
from fil_shop.store import Store

MARKER = "evaluation-root.json"
ROOT_IDENTITY = {"schema": 1, "purpose": "fil-isolated-evaluation-inventory"}
CONVERSATION = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class EvaluationStore:
    """Persistent per-conversation real Stores, addressed only by trusted conversation IDs."""

    def __init__(self, root: str | Path, *, resume: bool = False,
                 clock: Callable[[], float] = time.time):
        path = Path(root)
        if path.is_symlink():
            raise ValueError("Evaluation root must not be a symlink")
        if resume:
            marker = path / MARKER
            if not path.is_dir() or marker.is_symlink() or not marker.is_file():
                raise ValueError("Resume requires a marked evaluation root")
            try:
                identity = json.loads(marker.read_text())
            except (OSError, ValueError) as exc:
                raise ValueError("Invalid evaluation root marker") from exc
            if identity != ROOT_IDENTITY:
                raise ValueError("Evaluation root marker does not match this evaluator")
        else:
            # Never reset an existing run or silently adopt an arbitrary/live database directory.
            path.mkdir(parents=True, exist_ok=False)
            (path / MARKER).write_text(json.dumps(ROOT_IDENTITY, indent=2) + "\n")
        self.root, self.clock = path.resolve(), clock
        self._stores: dict[str, Store] = {}
        self._lock = threading.Lock()

    def database_path(self, conversation: str) -> Path:
        if not CONVERSATION.fullmatch(conversation):
            raise ValueError("Invalid provider conversation ID")
        digest = hashlib.sha256(conversation.encode()).hexdigest()
        return self.root / f"{digest}.sqlite"

    def __call__(self, conversation: str) -> Store:
        path = self.database_path(conversation)
        with self._lock:
            if path.is_symlink():
                raise ValueError("Evaluation conversation database must not be a symlink")
            if conversation not in self._stores:
                self._stores[conversation] = Store(path, self.clock)
            return self._stores[conversation]


def create_evaluation_app(root: str | Path, webhook_secret: str, *, resume: bool = False,
                          clock: Callable[[], float] = time.time) -> FastAPI:
    if len(webhook_secret) < 32 or not webhook_secret.isascii():
        raise ValueError("FIL_EVALUATION_WEBHOOK_SECRET must be at least 32 ASCII characters")
    router = EvaluationStore(root, resume=resume, clock=clock)
    # Same tools, errors, Store and transactions; deliberately no browser routes, static or tokens.
    return create_app(None, webhook_secret, clock, store_for_conversation=router, enable_demo=False)
