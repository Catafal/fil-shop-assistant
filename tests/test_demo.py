import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from fil_shop.api import create_app
from fil_shop.demo import DemoSettings
from fil_shop.store import Store

SECRET = "synthetic-fil-browser-credential-00000000000"
ORIGIN = "http://localhost:8000"
CRITERIA = {"category": "shirt", "occasion": "wedding", "max_price_cents": 12000,
            "colour": "navy", "size": "M"}


class Tokens:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        return {"token": f"synthetic-provider-token-{self.count}",
                "conversation_id": f"conv-shop-{self.count}"}


@pytest.fixture
def demo(tmp_path):
    now = [datetime(2026, 11, 5, 10, tzinfo=ZoneInfo("Europe/Madrid")).timestamp()]
    tokens = Tokens()
    path = tmp_path / "fil.sqlite"
    app = create_app(str(path), SECRET, lambda: now[0], token_getter=tokens)
    client = TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50000))
    assert client.get("/demo/config").status_code == 200
    return client, tokens, now, path, app


def start(client, scenario="normal"):
    return client.post("/demo/sessions", json={"scenario": scenario}, headers={"Origin": ORIGIN})


def control(client, path):
    return client.post(f"/demo/session/{path}", headers={"Origin": ORIGIN})


def tool(client, conv, kind, body):
    return client.post(f"/shop/{kind}", headers={"Authorization": f"Bearer {SECRET}",
                                               "X-Conversation-ID": conv}, json=body)


def search(client, conv, **changes):
    return tool(client, conv, "search", {**CRITERIA, **changes})


def checked(client, conv):
    return tool(client, conv, "check", {"sku": "FIL01-M-NAVY", "destination": "Barcelona",
                                       "requested_date": "2026-11-20",
                                       "requested_date_text": "2026-11-20", "delivery_method": "standard"})


def held(client, conv):
    search(client, conv)
    q = checked(client, conv).json()["quote_id"]
    return tool(client, conv, "reserve", {"quote_id": q})


def state(client):
    return client.get("/demo/session").json()


def guided_start(client, scenario="normal", restart_from=None):
    return client.post("/demo/guided", json={"scenario": scenario, "restart_from": restart_from},
                       headers={"Origin": ORIGIN})


def guided_action(client, identifier, action):
    return client.post("/demo/guided/action", json={"id": identifier, "action": action},
                       headers={"Origin": ORIGIN})


def test_guided_shop_works_without_provider_or_shared_stock(tmp_path):
    path = tmp_path / "live.sqlite"
    app = create_app(str(path), SECRET)
    with (TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50000)) as first,
          TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50001)) as second):
        assert first.get("/demo/config").json()["configured"] is False
        second.get("/demo/config").raise_for_status()
        initial = guided_start(first).json()
        identifier = initial["view"]["session"]["id"]
        assert initial["stage"] == "initial"
        assert [product["id"] for product in initial["view"]["products"]] == ["fil-01", "fil-03"]
        assert guided_start(first).json() == initial
        assert guided_action(first, identifier, "reserve").status_code == 409
        assert second.get("/demo/guided").json() is None
        other = guided_start(second).json()["view"]["session"]["id"]
        assert guided_action(second, identifier, "change-colour").status_code == 409

        revised = guided_action(first, identifier, "change-colour").json()
        assert revised["view"]["criteria"] == {**CRITERIA, "colour": "sage"}
        assert [product["id"] for product in revised["view"]["products"]] == ["fil-02"]
        assert guided_action(first, identifier, "change-colour").json() == revised
        quote = guided_action(first, identifier, "check").json()["view"]["quote"]
        assert quote["sku"] == "FIL02-M-SAGE" and quote["shipping_cents"] == 495
        held = guided_action(first, identifier, "reserve").json()
        assert held["stage"] == "held"
        assert guided_action(first, identifier, "reserve").json() == held
        retry = guided_action(first, identifier, "retry").json()["view"]["last_retry"]
        assert retry["created"] is False
        assert retry["reservation"]["id"] == held["view"]["reservation"]["id"]
        assert first.get("/demo/session").json()["session"] is None

        guided_action(second, other, "change-colour").raise_for_status()
        other_quote = guided_action(second, other, "check").json()["view"]
        assert other_quote["checked"]["available_quantity"] == 3
        declined = guided_action(second, other, "decline").json()
        assert declined["stage"] == "declined"
        assert declined["view"]["reservation"] is None
        assert guided_action(second, other, "reserve").status_code == 409
        assert first.get("/demo/guided").json()["view"]["reservation"]["id"] == retry["reservation"]["id"]

    with Store(path).connection() as db:
        assert db.execute("SELECT count(*) FROM shopping_contexts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 0


def test_guided_origin_expiry_and_restart(demo):
    client, tokens, now, _, _ = demo
    assert client.post("/demo/guided", json={"scenario": "normal"}).status_code == 403
    initial = guided_start(client).json()
    identifier = initial["view"]["session"]["id"]
    outage = guided_start(client, "inventory-outage", identifier).json()
    assert outage["stage"] == "outage"
    assert outage["view"]["error"] == "inventory_unavailable"
    assert outage["view"]["events"][0]["status"] == 503
    assert guided_action(client, identifier, "change-colour").status_code == 409
    assert guided_start(client, "inventory-outage", identifier).json() == outage
    assert client.get("/demo/guided").headers["cache-control"] == "no-store"

    now[0] += 30 * 60
    assert client.get("/demo/guided").json() is None
    assert guided_action(client, outage["view"]["session"]["id"], "retry").status_code == 410
    assert guided_start(client).json()["stage"] == "initial"
    assert tokens.count == 0


def test_config_cookie_empty_cards_and_no_pin(demo):
    client, tokens, _, _, _ = demo
    response = client.get("/demo/config")
    assert response.json()["brand"] == "Fil"
    assert response.json()["configured"] is True
    assert response.json()["access_required"] is False
    assert "accounts" not in response.json()
    assert "pin" not in response.text
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "Path=/demo" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert state(client)["products"] == []
    assert state(client)["events"] == []
    assert tokens.count == 0


def test_owned_tool_observation_and_current_projection(demo):
    client, _, _, _, _ = demo
    minted = start(client).json()
    conv = minted["conversation_id"]
    assert state(client)["products"] == []
    result = search(client, conv)
    assert result.status_code == 200
    assert [p["id"] for p in state(client)["products"]] == ["fil-01", "fil-03"]
    assert checked(client, conv).status_code == 200
    snapshot = state(client)
    assert snapshot["quote"]["sku"] == "FIL01-M-NAVY"
    assert [e["kind"] for e in snapshot["events"]] == ["search", "check"]
    encoded = json.dumps(snapshot)
    assert minted["conversation_token"] not in encoded
    assert SECRET not in encoded
    assert "Authorization" not in encoded


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example"])
def test_mutations_reject_missing_or_foreign_origin(demo, origin):
    client, tokens, _, _, _ = demo
    response = client.post("/demo/sessions", json={"scenario": "normal"},
                           headers={"Origin": origin} if origin else {})
    assert response.status_code == 403
    assert response.json()["error"] == "origin_denied"
    assert tokens.count == 0


def test_remote_peer_and_tunnel_cannot_claim_local_by_headers(demo):
    _, tokens, _, _, app = demo
    remote = TestClient(app, base_url=ORIGIN, client=("203.0.113.10", 1234))
    assert remote.get("/demo/config", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
    tunnel = TestClient(app, base_url="https://public.example", client=("127.0.0.1", 1234))
    assert tunnel.get("/demo/config").status_code == 403
    assert tunnel.get("/demo/config", headers={"Host": "localhost:8000",
                                               "CF-Connecting-IP": "203.0.113.10"}).status_code == 403
    assert tokens.count == 0


def test_public_gate_secure_cookie_and_bounded_attempts(tmp_path):
    tokens = Tokens()
    origin = "https://demo.example"
    app = create_app(str(tmp_path / "fil.sqlite"), SECRET, token_getter=tokens,
                     demo_settings=DemoSettings(access_code="synthetic-access-code",
                                                origins=(origin,), secure_cookies=True))
    client = TestClient(app, base_url=origin, client=("203.0.113.10", 1234))
    config = client.get("/demo/config")
    assert config.json()["access_required"] is True
    assert "Secure" in config.headers["set-cookie"]
    assert client.post("/demo/sessions", headers={"Origin": origin},
                       json={"scenario": "normal"}).status_code == 403
    for _ in range(4):
        assert client.post("/demo/access", headers={"Origin": origin},
                           json={"code": "wrong"}).status_code == 403
    assert client.post("/demo/access", headers={"Origin": origin},
                       json={"code": "synthetic-access-code"}).status_code == 200
    assert client.post("/demo/access", headers={"Origin": origin},
                       json={"code": "synthetic-access-code"}).status_code == 429
    assert client.post("/demo/sessions", headers={"Origin": origin},
                       json={"scenario": "normal"}).status_code == 200
    assert tokens.count == 1


def test_public_gate_refuses_insecure_cookie_configuration(tmp_path):
    tokens = Tokens()
    app = create_app(str(tmp_path / "fil.sqlite"), SECRET, token_getter=tokens,
                     demo_settings=DemoSettings(access_code="synthetic-access-code"))
    client = TestClient(app, base_url="https://demo.example", client=("203.0.113.10", 1234))
    assert client.get("/demo/config").json()["error"] == "secure_cookie_required"
    assert tokens.count == 0


def test_session_isolation_selectors_and_simulation_independence(demo):
    client, _, _, _, app = demo
    conv = start(client).json()["conversation_id"]
    search(client, conv)
    search(client, "native-simulation", colour="sage")
    assert len(state(client)["events"]) == 1
    assert state(client)["criteria"]["colour"] == "navy"
    other = TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50001))
    other.get("/demo/config")
    assert state(other)["products"] == []
    assert other.get(f"/demo/session?conversation_id={conv}").status_code == 422
    assert other.post("/demo/sessions", headers={"Origin": ORIGIN},
                      json={"scenario": "normal", "conversation_id": conv}).status_code == 422
    assert control(other, "retry").status_code == 409
    assert client.post("/shop/search", json=CRITERIA,
                       headers={"X-Conversation-ID": conv}).status_code == 401
    assert len(state(client)["events"]) == 1


def test_double_start_and_issuance_caps(demo):
    client, tokens, _, _, _ = demo
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(client), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert tokens.count == 1
    control(client, "end")
    for _ in range(4):
        assert start(client).status_code == 200
        assert control(client, "end").status_code == 200
    assert start(client).status_code == 429
    assert tokens.count == 5


def test_global_issuance_cap_survives_new_browser_owners(demo):
    _, tokens, _, _, app = demo
    for index in range(20):
        client = TestClient(app, base_url=ORIGIN, client=(f"127.0.0.{index + 1}", 1000))
        client.get("/demo/config")
        assert start(client).status_code == 200
    blocked = TestClient(app, base_url=ORIGIN, client=("127.0.0.99", 1000))
    blocked.get("/demo/config")
    assert start(blocked).status_code == 429
    assert tokens.count == 20


def test_missing_provider_identity_and_exception_do_not_leak(tmp_path):
    outcomes = [{"token": "unmapped-private-capability"}, RuntimeError("private-provider-secret")]

    def getter():
        result = outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    app = create_app(str(tmp_path / "fil.sqlite"), SECRET, token_getter=getter)
    client = TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1234))
    client.get("/demo/config")
    for _ in range(2):
        result = start(client)
        assert result.status_code == 503
        assert result.json() == {"error": "provider_unavailable"}
    assert state(client)["session"] is None


def test_context_change_failure_and_expiry_clear_current_quote(demo):
    client, _, now, _, _ = demo
    conv = start(client).json()["conversation_id"]
    search(client, conv)
    checked(client, conv)
    assert state(client)["quote"]
    now[0] += 120
    assert state(client)["quote"] is None
    assert state(client)["checked"]["quote_id"] is None
    search(client, conv, colour="sage", size="L")
    assert state(client)["checked"] is None
    assert [p["id"] for p in state(client)["products"]] == ["fil-02"]
    assert tool(client, conv, "search", {"size": "invented"}).status_code == 422
    assert state(client)["products"] == []
    assert state(client)["error"] == "invalid_request"
    now[0] += 1680
    assert client.get("/demo/session").status_code == 410
    assert control(client, "retry").status_code == 410


def test_late_old_tool_response_cannot_restore_old_current_context(demo, monkeypatch):
    client, _, _, _, _ = demo
    conv = start(client).json()["conversation_id"]
    original = Store.search

    def new_intent_after_old_result(self, conversation, criteria):
        old = original(self, conversation, criteria)
        original(self, conversation, {**criteria, "colour": "sage", "size": "L"})
        return old

    monkeypatch.setattr(Store, "search", new_intent_after_old_result)
    response = search(client, conv)
    snapshot = state(client)
    assert response.json()["criteria"]["colour"] == "navy"
    assert snapshot["criteria"]["colour"] == "sage"
    assert [p["id"] for p in snapshot["products"]] == ["fil-02"]
    assert snapshot["revision"] > snapshot["events"][-1]["payload"]["revision"]


def test_actual_inventory_outage_scoped_to_owned_browser_only(demo):
    client, _, _, _, app = demo
    conv = start(client, "inventory-outage").json()["conversation_id"]
    assert search(client, conv).status_code == 503
    assert state(client)["products"] == []
    assert state(client)["error"] == "inventory_unavailable"
    assert state(client)["events"][-1]["status"] == 503
    assert search(client, "normal-native-simulation").status_code == 200
    other = TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50001))
    other.get("/demo/config")
    normal = start(other).json()["conversation_id"]
    assert search(other, normal).status_code == 200


def test_operator_retry_only_existing_hold_after_quote_expiry_and_terminal_hold_expiry(demo):
    client, _, now, _, _ = demo
    conv = start(client).json()["conversation_id"]
    assert control(client, "retry").status_code == 409
    original = held(client, conv).json()
    now[0] += 120
    retried = control(client, "retry")
    assert retried.status_code == 200
    assert retried.json()["created"] is False
    assert retried.json()["reservation"]["id"] == original["reservation"]["id"]
    assert state(client)["events"][-1]["kind"] == "operator_retry"
    assert client.post("/demo/session/retry", headers={"Origin": ORIGIN},
                       json={"quote_id": "replacement"}).status_code == 422
    now[0] += 480
    assert control(client, "retry").status_code == 410
    assert state(client)["reservation"]["status"] == "expired"
    assert state(client)["last_retry"] is None


def test_static_fallback_never_masks_shop_or_legacy_api_404s(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>Fil</h1>")
    app = create_app(str(tmp_path / "fil.sqlite"), SECRET,
                     demo_settings=DemoSettings(static_dir=str(static)))
    client = TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 1234))
    assert "Fil" in client.get("/").text
    assert client.get("/shop/not-real").status_code == 404
    assert client.get("/billing/latest").status_code == 404
    assert client.get("/demo/not-real").status_code == 404


def test_main_uses_separate_fil_database_and_ignores_legacy_path(monkeypatch):
    from fil_shop import main
    captured = []
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("FIL_DB_PATH", raising=False)
    monkeypatch.setenv("TELECAT_DB_PATH", "data/do-not-open-old-fil_shop.sqlite")
    monkeypatch.setattr(main, "create_app", lambda path, secret, **kwargs: captured.append(path))
    main.app()
    assert captured == ["data/fil.sqlite"]


def test_retry_observation_from_expired_hold_is_not_projected_for_new_hold(demo):
    client, _, now, _, _ = demo
    conv = start(client).json()["conversation_id"]
    first = held(client, conv).json()["reservation"]
    assert control(client, "retry").status_code == 200
    assert state(client)["last_retry"]["reservation"]["id"] == first["id"]
    now[0] += 601
    second = held(client, conv).json()["reservation"]
    assert second["id"] != first["id"]
    snapshot = state(client)
    assert snapshot["reservation"]["id"] == second["id"]
    assert snapshot["last_retry"] is None
    history = [event for event in snapshot["events"] if event["kind"] == "operator_retry"]
    assert history[-1]["payload"]["reservation"]["id"] == first["id"]
    assert control(client, "retry").json()["reservation"]["id"] == second["id"]
