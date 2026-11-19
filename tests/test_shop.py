import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from fil_shop.api import create_app
from fil_shop.store import Store

SECRET = "synthetic-shop-credential-00000000000000000"
ZONE = ZoneInfo("Europe/Madrid")


def timestamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=ZONE).timestamp()


@pytest.fixture
def shop(tmp_path):
    now = [timestamp("2026-11-05T10:00:00")]
    path = tmp_path / "fil.sqlite"
    client = TestClient(create_app(str(path), SECRET, lambda: now[0]))
    return client, path, now


def headers(conversation="shop-a"):
    return {"Authorization": f"Bearer {SECRET}", "X-Conversation-ID": conversation}


def criteria(**changes):
    return {"category": None, "occasion": "wedding", "max_price_cents": 12000,
            "colour": None, "size": "M", **changes}


def search(client, conversation="shop-a", **changes):
    return client.post("/shop/search", json=criteria(**changes), headers=headers(conversation))


def check(client, conversation="shop-a", **changes):
    body = {"sku": "FIL01-M-NAVY", "destination": "Barcelona", "requested_date": "2026-11-11",
            "delivery_method": "standard", **changes}
    body.setdefault("requested_date_text", body["requested_date"])
    return client.post("/shop/check", json=body, headers=headers(conversation))


def reserve(client, quote, conversation="shop-a"):
    return client.post("/shop/reserve", json={"quote_id": quote}, headers=headers(conversation))


def quote(client, conversation="shop-a", **changes):
    assert search(client, conversation).status_code == 200
    return check(client, conversation, **changes).json()["quote_id"]


def test_real_filters_three_results_and_exact_variants(shop):
    client, _, _ = shop
    response = search(client)
    assert response.status_code == 200
    result = response.json()
    assert [p["id"] for p in result["products"]] == ["fil-01", "fil-02", "fil-03"]
    assert result["timezone"] == "Europe/Madrid"
    assert result["server_time"].startswith("2026-11-05T10:00:00")
    filtered = search(client, category="shirt", colour="sage", max_price_cents=7000).json()
    assert [p["id"] for p in filtered["products"]] == ["fil-02"]
    assert any(v["sku"] == "FIL02-M-SAGE" for v in filtered["products"][0]["variants"])
    assert filtered["products"][0]["image_path"] == "/products/fil-02.svg"
    assert search(client, max_price_cents=4000).json()["products"] == []


def test_price_is_one_item_and_delivery_is_separate(shop):
    client, _, _ = shop
    search(client)
    result = check(client).json()
    assert result["price_cents"] == 5900
    assert result["shipping_cents"] == 495
    assert result["size"] == "M" and result["colour"] == "navy"
    assert result["garment_measurements"] == {"chest_cm": 108, "length_cm": 72}
    assert result["quote_id"]


@pytest.mark.parametrize("path,body", [
    ("/shop/search", criteria()),
    ("/shop/check", {"sku": "FIL01-M-NAVY", "destination": "Barcelona",
                     "requested_date": "2026-11-11", "delivery_method": "standard"}),
    ("/shop/reserve", {"quote_id": "not-a-quote"}),
])
def test_tools_require_provider_auth_and_fixed_conversation(shop, path, body):
    client, _, _ = shop
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=headers("{{system__conversation_id}}")).status_code == 400
    assert client.post(path + "?conversation_id=other", json=body,
                       headers=headers()).status_code == 422


def test_no_account_identity_or_legacy_tool_routes(shop):
    client, _, _ = shop
    assert search(client).status_code == 200
    assert client.post("/verify", json={"pin": "1001"}, headers=headers()).status_code == 404
    assert client.get("/billing/latest", headers=headers()).status_code == 404
    assert client.post("/tickets", json={}, headers=headers()).status_code == 404


def test_new_search_and_changed_check_supersede_quotes(shop):
    client, _, _ = shop
    old = quote(client)
    search(client, colour="sage")
    assert reserve(client, old).json()["error"] == "quote_superseded"
    assert check(client).json()["error"] == "variant_not_in_results"
    current = check(client, sku="FIL02-M-SAGE").json()["quote_id"]
    search(client, colour="ivory", size="L")
    later = check(client, sku="FIL02-L-IVORY", destination="Madrid", delivery_method="express").json()
    assert later["quote_id"] != current
    assert reserve(client, current).json()["error"] == "quote_superseded"
    assert reserve(client, later["quote_id"]).status_code == 200


def test_invalid_search_and_check_invalidate_previous_projection(shop):
    client, path, now = shop
    old = quote(client)
    assert client.post("/shop/search", json={"category": "invented"}, headers=headers()).status_code == 422
    projection = Store(path, lambda: now[0]).projection("shop-a")
    assert projection["products"] == [] and projection["quote"] is None
    assert projection["error"] == "invalid_request"
    assert reserve(client, old).status_code == 409
    old = quote(client)
    assert client.post("/shop/check", json={"sku": "FIL01-M-NAVY"}, headers=headers()).status_code == 422
    projection = Store(path, lambda: now[0]).projection("shop-a")
    assert projection["checked"] is None and projection["quote"] is None
    assert reserve(client, old).status_code == 409


@pytest.mark.parametrize("now,method,dispatch,arrival,cost", [
    ("2026-11-06T11:59:59", "standard", "2026-11-06", "2026-11-10", 495),
    ("2026-11-06T12:00:00", "standard", "2026-11-09", "2026-11-11", 495),
    ("2026-11-07T10:00:00", "express", "2026-11-09", "2026-11-10", 995),
    ("2026-11-08T10:00:00", "standard", "2026-11-09", "2026-11-11", 495),
    ("2026-11-05T10:00:00", "express", "2026-11-05", "2026-11-06", 995),
])
def test_documented_cutoff_weekends_and_methods(shop, now, method, dispatch, arrival, cost):
    client, _, clock = shop
    clock[0] = timestamp(now)
    search(client)
    result = check(client, delivery_method=method, requested_date="2026-11-20").json()
    assert result["dispatch_date"] == dispatch
    assert result["estimated_arrival_date"] == arrival
    assert result["shipping_cents"] == cost
    assert result["eligible_by_requested_date"] is True


@pytest.mark.parametrize("change,reason", [
    ({"destination": "unknown"}, "unknown_destination"),
    ({"destination": "València"}, "unknown_destination"),
    ({"requested_date": "Friday"}, "invalid_date"),
    ({"requested_date": "2026-11-04"}, "past_date"),
    ({"requested_date": "2026-11-06"}, "late_delivery"),
])
def test_unknown_or_unmet_delivery_never_quotes(shop, change, reason):
    client, _, _ = shop
    search(client)
    result = check(client, **change).json()
    assert result["reason"] == reason
    assert result["quote_id"] is None and result["quote_expires_at"] is None
    if reason == "unknown_destination":
        assert result["shipping_cents"] is None
        assert result["estimated_arrival_date"] is None
        assert result["eligible_by_requested_date"] is None


def test_no_stock_variant_is_not_quoted(shop):
    client, _, _ = shop
    search(client, category="shirt", colour="black", size="L")
    result = check(client, sku="FIL03-L-BLACK").json()
    assert result["available_quantity"] == 0
    assert result["reason"] == "out_of_stock"
    assert result["quote_id"] is None


def test_unavailable_inventory_fixture_is_unknown_not_zero(shop):
    client, _, _ = shop
    result = search(client, category="jacket", colour="ivory").json()
    product = next(p for p in result["products"] if p["id"] == "fil-08")
    variant = next(v for v in product["variants"] if v["sku"] == "FIL08-M-IVORY")
    assert variant["available_quantity"] is None
    assert variant["inventory_status"] == "unavailable"
    checked = check(client, sku="FIL08-M-IVORY")
    assert checked.status_code == 503
    assert checked.json()["error"] == "inventory_unavailable"
    search(client, category="jacket", colour="ivory", size="L")
    assert check(client, sku="FIL08-L-IVORY").status_code == 200


def test_quote_ownership_expiry_and_retry_before_expiry_validation(shop):
    client, _, now = shop
    q = quote(client)
    assert reserve(client, q, "different-conversation").status_code == 404
    first = reserve(client, q).json()
    assert first["created"] is True
    assert first["reservation"]["product_name"] == "Camisa Brisa"
    now[0] += 120
    retried = reserve(client, q).json()
    assert retried["created"] is False
    assert retried["reservation"]["id"] == first["reservation"]["id"]
    search(client, colour="sage")
    assert reserve(client, q).json()["reservation"]["id"] == first["reservation"]["id"]
    now[0] += 480
    assert reserve(client, q).json()["error"] == "reservation_expired"
    fresh = quote(client)
    assert reserve(client, fresh).status_code == 200


def test_unreserved_quote_expires_at_two_minutes(shop):
    client, path, now = shop
    q = quote(client)
    now[0] += 120
    assert reserve(client, q).status_code == 410
    assert reserve(client, q).json()["error"] == "quote_expired"
    current = Store(path, lambda: now[0]).projection("shop-a")
    assert current["quote"] is None
    assert current["checked"]["quote_id"] is None
    assert current["checked"]["reason"] == "quote_expired"


def test_one_live_hold_not_one_ever_and_restart_preserves_stock(shop):
    client, path, now = shop
    q = quote(client)
    first = reserve(client, q).json()["reservation"]
    search(client, colour="navy", size="L")
    other = check(client, sku="FIL01-L-NAVY").json()["quote_id"]
    assert reserve(client, other).json()["error"] == "active_reservation"
    restart = TestClient(create_app(str(path), SECRET, lambda: now[0]))
    assert reserve(restart, q).json()["reservation"]["id"] == first["id"]
    assert next(v for v in search(restart).json()["products"][0]["variants"]
                if v["sku"] == "FIL01-M-NAVY")["available_quantity"] == 0
    now[0] += 600
    assert next(v for v in search(restart).json()["products"][0]["variants"]
                if v["sku"] == "FIL01-M-NAVY")["available_quantity"] == 1
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 1


def test_last_unit_race_uses_independent_apps_and_connections(shop):
    first, path, now = shop
    second = TestClient(create_app(str(path), SECRET, lambda: now[0]))
    qa, qb = quote(first, "race-a"), quote(second, "race-b")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve, first, qa, "race-a"),
                   pool.submit(reserve, second, qb, "race-b")]
        responses = [f.result() for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r.json()["error"] for r in responses if r.status_code == 409) == "out_of_stock"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 1


def test_concurrent_exact_retries_and_retry_only_never_first_write(shop):
    client, path, now = shop
    q = quote(client)
    store = Store(path, lambda: now[0])
    assert store.reserve("shop-a", q, existing_only=True)[0] == "retry_unavailable"
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: store.reserve("shop-a", q), range(3)))
    assert all(code == "ok" for code, _ in results)
    assert sum(result["created"] for _, result in results) == 1
    assert len({result["reservation"]["id"] for _, result in results}) == 1


def test_seed_never_resets_stock(shop):
    _, path, now = shop
    with sqlite3.connect(path) as db:
        db.execute("UPDATE variants SET stock_on_hand=7 WHERE sku='FIL01-M-NAVY'")
    Store(path, lambda: now[0])
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT stock_on_hand FROM variants WHERE sku='FIL01-M-NAVY'").fetchone()[0] == 7
        assert db.execute("SELECT count(*) FROM products").fetchone()[0] == 8


def test_missing_operational_secret_has_no_default(tmp_path):
    with pytest.raises(ValueError, match="FIL_WEBHOOK_SECRET"):
        create_app(str(tmp_path / "fil.sqlite"), "")


def test_expiry_uses_time_after_database_acquisition(shop, monkeypatch):
    client, _, now = shop
    q = quote(client)
    original_connection = Store.connection

    @contextmanager
    def delayed_connection(self):
        with original_connection(self) as db:
            now[0] += 120
            yield db

    monkeypatch.setattr(Store, "connection", delayed_connection)
    response = reserve(client, q)
    assert response.status_code == 410
    assert response.json()["error"] == "quote_expired"


@pytest.mark.parametrize("sku", ["FIL01-L-NAVY", "FIL01-M-IVORY", "FIL01-L-IVORY"])
def test_exact_variant_cannot_silently_relax_current_search_preferences(shop, sku):
    client, path, now = shop
    search(client, colour="navy", size="M")
    valid_quote = check(client).json()["quote_id"]
    mismatched = check(client, sku=sku)
    assert mismatched.status_code == 409
    assert mismatched.json()["error"] == "variant_not_in_results"
    projection = Store(path, lambda: now[0]).projection("shop-a")
    assert projection["criteria"]["colour"] == "navy"
    assert projection["criteria"]["size"] == "M"
    assert projection["quote"] is None
    assert reserve(client, valid_quote).json()["error"] == "quote_superseded"


@pytest.mark.parametrize("unknown", [False, True])
def test_refreshed_zero_or_unknown_inventory_is_not_currently_reservable(shop, unknown):
    client, path, now = shop
    q = quote(client)
    with sqlite3.connect(path) as db:
        if unknown:
            db.execute("UPDATE variants SET inventory_available=0 WHERE sku='FIL01-M-NAVY'")
        else:
            db.execute("UPDATE variants SET stock_on_hand=0 WHERE sku='FIL01-M-NAVY'")
    projection = Store(path, lambda: now[0]).projection("shop-a")
    assert projection["checked"]["available_quantity"] == (None if unknown else 0)
    assert projection["quote"] is None
    assert projection["checked"]["quote_id"] is None
    assert projection["error"] == ("inventory_unavailable" if unknown else "out_of_stock")
    assert reserve(client, q).json()["error"] == projection["error"]


def test_current_catalogue_price_cannot_escape_search_budget(shop):
    client, path, _ = shop
    search(client, max_price_cents=6000)
    with sqlite3.connect(path) as db:
        product = json.loads(db.execute("SELECT data FROM products WHERE id='fil-01'").fetchone()[0])
        product["price_cents"] = 7000
        db.execute("UPDATE products SET data=? WHERE id='fil-01'", (json.dumps(product),))
    assert check(client).json()["error"] == "variant_not_in_results"


@pytest.mark.parametrize("phrase", [
    "Saturday, 2026-11-20", "dissabte, 20 de novembre", "SÁBADO, 20 de noviembre",
    "by Thursday or Friday, November twentieth", "dijous o divendres, 20 de novembre",
    "miércoles, 20 de noviembre",
])
def test_conflicting_weekday_requires_clarification_and_supersedes_quote(shop, phrase):
    client, path, now = shop
    prior = quote(client, requested_date="2026-11-20")
    response = check(client, requested_date="2026-11-20", requested_date_text=phrase)
    assert response.status_code == 409
    result = response.json()
    assert result["error"] == "date_clarification_required"
    assert result["expected_weekday"] == "Friday"
    assert result["quote_id"] is None
    assert not {"available_quantity", "price_cents", "estimated_arrival_date"}.intersection(result)
    snapshot = Store(path, lambda: now[0]).projection("shop-a")
    assert snapshot["checked"] is None and snapshot["quote"] is None
    assert reserve(client, prior).json()["error"] == "quote_superseded"
    corrected = check(client, requested_date="2026-11-20",
                      requested_date_text="Friday, November twentieth").json()
    assert corrected["quote_id"]


@pytest.mark.parametrize("phrase", [
    "Friday, 2026-11-20", "DIVENDRES, 20 de novembre", "viernes 20 de noviembre",
    "November twentieth, 2026", "2026-11-20", "Friday's wedding, November twentieth",
])
def test_matching_or_unspecified_weekday_preserves_quote_path(shop, phrase):
    client, _, _ = shop
    search(client)
    result = check(client, requested_date="2026-11-20", requested_date_text=phrase)
    assert result.status_code == 200
    assert result.json()["quote_id"]


def test_missing_literal_date_field_rejected_and_clears_prior_quote(shop):
    client, path, now = shop
    prior = quote(client)
    response = client.post("/shop/check", headers=headers(), json={
        "sku": "FIL01-M-NAVY", "destination": "Barcelona", "requested_date": "2026-11-20",
        "delivery_method": "standard",
    })
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert reserve(client, prior).json()["error"] == "quote_superseded"
    assert Store(path, lambda: now[0]).projection("shop-a")["checked"] is None
