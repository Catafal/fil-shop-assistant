import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from fil_shop.api import create_app
from fil_shop.demo import DemoSettings
from fil_shop.evaluation import MARKER, EvaluationStore, create_evaluation_app

SECRET = "evaluation-only-synthetic-secret-00000000000"
NOW = datetime(2026, 11, 5, 10, tzinfo=ZoneInfo("Europe/Madrid")).timestamp()
CRITERIA = {"category": "shirt", "occasion": "wedding", "max_price_cents": 12000,
            "colour": "navy", "size": "M"}
CHECK = {"sku": "FIL01-M-NAVY", "destination": "Barcelona", "requested_date": "2026-11-20",
         "requested_date_text": "2026-11-20", "delivery_method": "standard"}


def tool(client, conversation, kind, body, secret=SECRET):
    return client.post(f"/shop/{kind}", json=body,
                       headers={"Authorization": f"Bearer {secret}", "X-Conversation-ID": conversation})


def quote(client, conversation):
    assert tool(client, conversation, "search", CRITERIA).status_code == 200
    response = tool(client, conversation, "check", CHECK)
    assert response.status_code == 200
    return response.json()["quote_id"]


def hold(client, conversation, quote_id):
    return tool(client, conversation, "reserve", {"quote_id": quote_id})


def test_isolated_last_unit_and_persistent_retry_after_restart(tmp_path):
    root = tmp_path / "run"
    now = [NOW]
    client = TestClient(create_evaluation_app(root, SECRET, clock=lambda: now[0]))
    quotes = {conv: quote(client, conv) for conv in ("model-a", "model-b")}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda conv: hold(client, conv, quotes[conv]), quotes))
    assert [result.status_code for result in results] == [200, 200]
    ids = [result.json()["reservation"]["id"] for result in results]
    assert len(set(ids)) == 2
    assert len(list(root.glob("*.sqlite"))) == 2
    now[0] += 121  # Exact retries still resolve an existing hold after quote expiry.
    restarted = TestClient(create_evaluation_app(root, SECRET, resume=True, clock=lambda: now[0]))
    for index, conv in enumerate(quotes):
        response = hold(restarted, conv, quotes[conv])
        assert response.status_code == 200
        assert response.json()["reservation"]["id"] == ids[index]
    # A third independent conversation still starts with its own last unit.
    assert hold(restarted, "model-c", quote(restarted, "model-c")).status_code == 200
    now[0] += 480
    assert hold(restarted, "model-a", quotes["model-a"]).status_code == 410


def test_production_still_shares_last_unit(tmp_path):
    client = TestClient(create_app(str(tmp_path / "live.sqlite"), SECRET, lambda: NOW))
    first, second = quote(client, "a"), quote(client, "b")
    assert hold(client, "a", first).status_code == 200
    response = hold(client, "b", second)
    assert response.status_code == 409
    assert response.json()["error"] == "out_of_stock"


def test_tool_only_surface_and_auth_do_not_create_inventory(tmp_path):
    root = tmp_path / "run"
    app = create_evaluation_app(root, SECRET, clock=lambda: NOW)
    assert {(route.path, tuple(sorted(route.methods))) for route in app.routes} == {
        (f"/shop/{kind}", ("POST",)) for kind in ("search", "check", "reserve")}
    client = TestClient(app)
    for path in ("/", "/products/fil-01.svg", "/demo/config", "/demo/access", "/demo/sessions",
                 "/demo/session", "/demo/session/end", "/demo/session/retry"):
        assert client.get(path).status_code == 404
        assert client.post(path, json={}).status_code == 404
    assert tool(client, "a", "search", CRITERIA, "production-secret-does-not-work").status_code == 401
    assert tool(client, "../escape", "search", CRITERIA).status_code == 400
    assert list(root.glob("*.sqlite")) == []
    for kwargs in ({"token_getter": dict}, {"demo_settings": DemoSettings()}):
        with pytest.raises(ValueError, match="Tool-only"):
            create_app(str(tmp_path / "other.sqlite"), SECRET, enable_demo=False, **kwargs)


def test_explicit_fresh_root_resume_and_paths(tmp_path):
    root = tmp_path / "run"
    router = EvaluationStore(root, clock=lambda: NOW)
    assert router("a") is router("a")
    assert router.database_path("a").parent == root
    assert router.database_path("a").name != "a.sqlite"
    for bad in ("../outside", "a/b", "", "x" * 129):
        with pytest.raises(ValueError, match="conversation"):
            router(bad)
    with pytest.raises(FileExistsError):
        EvaluationStore(root)
    EvaluationStore(root, resume=True)
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    with pytest.raises(ValueError, match="marked"):
        EvaluationStore(unmarked, resume=True)
    (unmarked / MARKER).write_text(json.dumps({"purpose": "production"}))
    with pytest.raises(ValueError, match="marker"):
        EvaluationStore(unmarked, resume=True)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        EvaluationStore(alias, resume=True)
    router.database_path("b").symlink_to(router.database_path("a"))
    with pytest.raises(ValueError, match="symlink"):
        router("b")
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="FIL_EVALUATION_WEBHOOK_SECRET"):
        create_evaluation_app(missing, "")
    assert not missing.exists()


def test_invalid_request_does_not_clear_other_conversations_quote(tmp_path):
    client = TestClient(create_evaluation_app(tmp_path / "run", SECRET, clock=lambda: NOW))
    first, second = quote(client, "a"), quote(client, "b")
    assert tool(client, "a", "check", {}).status_code == 422
    assert hold(client, "a", first).status_code == 409
    assert hold(client, "b", second).status_code == 200


def test_unknown_and_real_zero_stock_keep_real_store_errors(tmp_path):
    client = TestClient(create_evaluation_app(tmp_path / "run", SECRET, clock=lambda: NOW))
    for conv, sku, category, colour, expected in (
        ("unknown", "FIL08-M-IVORY", "jacket", "ivory", 503),
        ("zero", "FIL03-L-BLACK", "shirt", "black", 200),
    ):
        size = "L" if conv == "zero" else "M"
        criteria = {**CRITERIA, "category": category, "colour": colour, "size": size,
                    "max_price_cents": 20000}
        assert tool(client, conv, "search", criteria).status_code == 200
        response = tool(client, conv, "check", {**CHECK, "sku": sku})
        assert response.status_code == expected
        if conv == "unknown":
            assert response.json()["error"] == "inventory_unavailable"
        else:
            assert response.json()["available_quantity"] == 0
            assert response.json()["quote_id"] is None
            assert response.json()["reason"] == "out_of_stock"


def test_same_resolver_drives_real_browser_projection_and_operator_retry(tmp_path):
    router = EvaluationStore(tmp_path / "run", clock=lambda: NOW)
    counter = iter(("browser-a", "browser-b"))
    app = create_app(None, SECRET, lambda: NOW, store_for_conversation=router,
                     token_getter=lambda: {"token": "synthetic", "conversation_id": next(counter)})
    origin = "http://localhost:8000"
    for conv in ("browser-a", "browser-b"):
        client = TestClient(app, base_url=origin, client=("127.0.0.1", 50000))
        assert client.get("/demo/config").status_code == 200
        minted = client.post("/demo/sessions", json={"scenario": "normal"}, headers={"Origin": origin})
        assert minted.json()["conversation_id"] == conv
        reserved = hold(client, conv, quote(client, conv)).json()["reservation"]
        assert client.get("/demo/session").json()["reservation"]["id"] == reserved["id"]
        retry = client.post("/demo/session/retry", headers={"Origin": origin})
        assert retry.status_code == 200
        assert retry.json()["reservation"]["id"] == reserved["id"]
        client.post("/demo/session/end", headers={"Origin": origin})


def test_startup_uses_only_separate_secret_and_explicit_root(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "scripts/run_evaluation_backend.py"
    spec = importlib.util.spec_from_file_location("evaluation_startup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("FIL_WEBHOOK_SECRET", SECRET)
    monkeypatch.delenv("FIL_EVALUATION_WEBHOOK_SECRET", raising=False)
    root = tmp_path / "run"
    monkeypatch.setattr("sys.argv", [str(path), "--root", str(root)])
    with pytest.raises(ValueError, match="FIL_EVALUATION_WEBHOOK_SECRET"):
        module.main()
    assert not root.exists()
    monkeypatch.setenv("FIL_EVALUATION_WEBHOOK_SECRET", SECRET)
    calls = []
    monkeypatch.setattr(module.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    module.main()
    assert calls[0][1] == {"host": "127.0.0.1", "port": 8001, "proxy_headers": False}
    client = TestClient(calls[0][0])
    assert client.get("/demo/config").status_code == 404
