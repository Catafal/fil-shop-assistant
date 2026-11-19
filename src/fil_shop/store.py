"""A synthetic shop: ordered context, fresh delivery quotes and atomic stock-backed holds."""

import json
import re
import secrets
import sqlite3
import time
import unicodedata
from collections.abc import Callable
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from datetime import time as day_time
from pathlib import Path
from zoneinfo import ZoneInfo

from fil_shop.catalogue import product_records

QUOTE_SECONDS = 120
HOLD_SECONDS = 600
ZONE = ZoneInfo("Europe/Madrid")
WEEKDAYS = (
    ("Monday", "dilluns", "lunes"), ("Tuesday", "dimarts", "martes"),
    ("Wednesday", "dimecres", "miercoles"), ("Thursday", "dijous", "jueves"),
    ("Friday", "divendres", "viernes"), ("Saturday", "dissabte", "sabado"),
    ("Sunday", "diumenge", "domingo"),
)


def conflicting_weekday(text: str, requested: date) -> str | None:
    # This checks submitted wording, not whether the model faithfully quoted the caller.
    normalized = "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                         if not unicodedata.combining(c))
    words = set(re.findall(r"[^\W\d_]+", normalized))
    for number, names in enumerate(WEEKDAYS):
        if number != requested.weekday() and any(name.casefold() in words for name in names):
            return names[0]
    return None


def shop_status(code: str) -> int:
    if code == "ok":
        return 200
    if code == "inventory_unavailable":
        return 503
    if code in ("quote_expired", "reservation_expired"):
        return 410
    if code == "quote_not_found":
        return 404
    return 409


class Store:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self.path, self.clock = str(path), clock
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS variants (
                    sku TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id),
                    size TEXT NOT NULL, colour TEXT NOT NULL,
                    stock_on_hand INTEGER NOT NULL CHECK(stock_on_hand >= 0),
                    inventory_available INTEGER NOT NULL CHECK(inventory_available IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS shopping_contexts (
                    conversation_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    criteria TEXT, result_ids TEXT NOT NULL DEFAULT '[]', checked TEXT,
                    quote_id TEXT, error TEXT
                );
                CREATE TABLE IF NOT EXISTS quotes (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, sku TEXT NOT NULL REFERENCES variants(sku),
                    item_price_cents INTEGER NOT NULL, shipping_cents INTEGER NOT NULL,
                    destination TEXT NOT NULL, requested_date TEXT NOT NULL,
                    delivery_method TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                    quote_id TEXT NOT NULL REFERENCES quotes(id), sku TEXT NOT NULL REFERENCES variants(sku),
                    created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    UNIQUE(conversation_id, quote_id)
                );
                CREATE INDEX IF NOT EXISTS live_holds ON reservations(sku, expires_at);
            """)
        self.seed()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for product, variants in product_records():
                db.execute("INSERT OR IGNORE INTO products VALUES (?, ?)",
                           (product["id"], json.dumps(product, ensure_ascii=False)))
                db.executemany("INSERT OR IGNORE INTO variants VALUES (?, ?, ?, ?, ?, ?)", variants)

    def server_time(self, now: float) -> dict:
        return {"server_time": datetime.fromtimestamp(now, ZONE).isoformat(), "timezone": "Europe/Madrid"}

    @staticmethod
    def context(db, conversation: str):
        db.execute("INSERT OR IGNORE INTO shopping_contexts (conversation_id, revision) VALUES (?, 0)",
                   (conversation,))
        return db.execute("SELECT * FROM shopping_contexts WHERE conversation_id=?", (conversation,)).fetchone()

    @staticmethod
    def availability(db, variant, now: float) -> int | None:
        if not variant["inventory_available"]:
            return None
        holds = db.execute("SELECT count(*) FROM reservations WHERE sku=? AND expires_at>?",
                           (variant["sku"], now)).fetchone()[0]
        return max(0, variant["stock_on_hand"] - holds)

    def product(self, db, product_id: str, now: float) -> dict:
        row = db.execute("SELECT data FROM products WHERE id=?", (product_id,)).fetchone()
        product = json.loads(row["data"])
        product["variants"] = [
            {"sku": v["sku"], "size": v["size"], "colour": v["colour"],
             "available_quantity": self.availability(db, v, now),
             "inventory_status": "available" if v["inventory_available"] else "unavailable"}
            for v in db.execute("SELECT * FROM variants WHERE product_id=? ORDER BY sku", (product_id,))
        ]
        return product

    def fail(self, conversation: str, kind: str, error: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            context = self.context(db, conversation)
            revision = context["revision"] + 1
            results = "[]" if kind == "search" else context["result_ids"]
            db.execute("UPDATE shopping_contexts SET revision=?, result_ids=?, checked=NULL, "
                       "quote_id=NULL, error=? WHERE conversation_id=?",
                       (revision, results, error, conversation))
            return {"error": error, "revision": revision}

    def search(self, conversation: str, criteria: dict) -> dict:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.clock()
            revision = self.context(db, conversation)["revision"] + 1
            products = []
            for row in db.execute("SELECT id FROM products ORDER BY id"):
                product = self.product(db, row["id"], now)
                if criteria["category"] and product["category"] != criteria["category"]:
                    continue
                if criteria["occasion"] not in product["occasion_tags"]:
                    continue
                if product["price_cents"] > criteria["max_price_cents"]:
                    continue
                if not any((not criteria["size"] or v["size"] == criteria["size"])
                           and (not criteria["colour"] or v["colour"] == criteria["colour"])
                           for v in product["variants"]):
                    continue
                products.append(product)
                if len(products) == 3:
                    break
            db.execute("UPDATE shopping_contexts SET revision=?, criteria=?, result_ids=?, "
                       "checked=NULL, quote_id=NULL, error=NULL WHERE conversation_id=?",
                       (revision, json.dumps(criteria), json.dumps([p["id"] for p in products]), conversation))
            return {"revision": revision, "criteria": criteria, "products": products, **self.server_time(now)}

    @staticmethod
    def business_days(start: date, days: int) -> date:
        while days:
            start += timedelta(days=1)
            if start.weekday() < 5:
                days -= 1
        return start

    def check(self, conversation: str, sku: str, destination: str,
              requested_date: str, delivery_method: str,
              requested_date_text: str | None = None) -> tuple[str, dict]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.clock()
            local = datetime.fromtimestamp(now, ZONE)
            context = self.context(db, conversation)
            revision = context["revision"] + 1
            db.execute("UPDATE shopping_contexts SET revision=?, checked=NULL, quote_id=NULL, "
                       "error=NULL WHERE conversation_id=?", (revision, conversation))
            if requested_date_text is not None:
                try:
                    parsed_date = date.fromisoformat(requested_date)
                except ValueError:
                    parsed_date = None
                stated = conflicting_weekday(requested_date_text, parsed_date) if parsed_date else None
                if stated:
                    db.execute("UPDATE shopping_contexts SET error='date_clarification_required' "
                               "WHERE conversation_id=?", (conversation,))
                    return "date_clarification_required", {
                        "error": "date_clarification_required", "revision": revision,
                        "requested_date": requested_date, "stated_weekday": stated,
                        "expected_weekday": WEEKDAYS[parsed_date.weekday()][0], "quote_id": None,
                    }
            variant = db.execute("SELECT * FROM variants WHERE sku=?", (sku,)).fetchone()
            if not variant or variant["product_id"] not in json.loads(context["result_ids"]):
                db.execute("UPDATE shopping_contexts SET error='variant_not_in_results' WHERE conversation_id=?",
                           (conversation,))
                return "variant_not_in_results", {"error": "variant_not_in_results", "revision": revision}
            product = self.product(db, variant["product_id"], now)
            criteria = json.loads(context["criteria"])
            if ((criteria["size"] and variant["size"] != criteria["size"])
                    or (criteria["colour"] and variant["colour"] != criteria["colour"])
                    or (criteria["category"] and product["category"] != criteria["category"])
                    or criteria["occasion"] not in product["occasion_tags"]
                    or product["price_cents"] > criteria["max_price_cents"]):
                db.execute("UPDATE shopping_contexts SET error='variant_not_in_results' WHERE conversation_id=?",
                           (conversation,))
                return "variant_not_in_results", {"error": "variant_not_in_results", "revision": revision}
            if not variant["inventory_available"]:
                db.execute("UPDATE shopping_contexts SET error='inventory_unavailable' WHERE conversation_id=?",
                           (conversation,))
                return "inventory_unavailable", {"error": "inventory_unavailable", "revision": revision}
            quantity = self.availability(db, variant, now)
            reason, dispatch, arrival, shipping, eligible, quote_id = None, None, None, None, None, None
            try:
                requested = date.fromisoformat(requested_date)
                if requested.isoformat() != requested_date:
                    raise ValueError("Not ISO date")
            except ValueError:
                requested, reason = None, "invalid_date"
            if requested is not None and requested < local.date():
                reason = "past_date"
            if destination not in ("Barcelona", "Madrid"):
                reason = "unknown_destination"
            if reason is None:
                dispatch = local.date()
                if local.weekday() >= 5 or local.time() >= day_time(12):
                    dispatch = self.business_days(dispatch, 1)
                arrival = self.business_days(dispatch, 2 if delivery_method == "standard" else 1)
                shipping = 495 if delivery_method == "standard" else 995
                eligible = arrival <= requested
                if not eligible:
                    reason = "late_delivery"
                elif quantity == 0:
                    reason = "out_of_stock"
            if reason is None:
                quote_id = "Q-" + secrets.token_hex(12)
                db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (quote_id, conversation, revision, sku, product["price_cents"], shipping,
                            destination, requested_date, delivery_method, now, now + QUOTE_SECONDS))
            result = {"revision": revision, "sku": sku, "product_id": variant["product_id"],
                      "size": variant["size"], "colour": variant["colour"], "available_quantity": quantity,
                      "price_cents": product["price_cents"],
                      "garment_measurements": product["garment_measurements"][variant["size"]],
                      "fit_notes": product["fit_notes"], "destination": destination,
                      "requested_date": requested_date, "delivery_method": delivery_method,
                      **self.server_time(now), "dispatch_date": dispatch.isoformat() if dispatch else None,
                      "estimated_arrival_date": arrival.isoformat() if arrival else None,
                      "shipping_cents": shipping, "eligible_by_requested_date": eligible,
                      "quote_id": quote_id, "quote_expires_at": now + QUOTE_SECONDS if quote_id else None,
                      "checked_at": now, "reason": reason}
            db.execute("UPDATE shopping_contexts SET checked=?, quote_id=? WHERE conversation_id=?",
                       (json.dumps(result), quote_id, conversation))
            return "ok", result

    @staticmethod
    def reservation(db, row, now: float) -> dict:
        quote = db.execute("SELECT * FROM quotes WHERE id=?", (row["quote_id"],)).fetchone()
        variant = db.execute("SELECT * FROM variants WHERE sku=?", (row["sku"],)).fetchone()
        product = json.loads(db.execute("SELECT data FROM products WHERE id=?",
                                        (variant["product_id"],)).fetchone()["data"])
        return {"id": row["id"], "quote_id": row["quote_id"], "sku": row["sku"],
                "product_id": variant["product_id"], "product_name": product["name"],
                "size": variant["size"], "colour": variant["colour"],
                **{k: quote[k] for k in ("item_price_cents", "shipping_cents", "destination",
                                        "requested_date", "delivery_method")},
                "created_at": row["created_at"], "expires_at": row["expires_at"],
                "status": "active" if row["expires_at"] > now else "expired"}

    def reserve(self, conversation: str, quote_id: str, *, existing_only: bool = False) -> tuple[str, dict]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Lock contention must not let a pre-lock timestamp revive an expired quote/hold.
            now = self.clock()
            context = self.context(db, conversation)
            prior = db.execute("SELECT * FROM reservations WHERE conversation_id=? AND quote_id=?",
                               (conversation, quote_id)).fetchone()
            if prior:
                if prior["expires_at"] <= now:
                    return "reservation_expired", {"error": "reservation_expired"}
                return "ok", {"reservation": self.reservation(db, prior, now), "created": False,
                              "revision": context["revision"]}
            if existing_only:
                return "retry_unavailable", {"error": "retry_unavailable"}
            quote = db.execute("SELECT * FROM quotes WHERE id=? AND conversation_id=?",
                               (quote_id, conversation)).fetchone()
            if quote is None:
                return "quote_not_found", {"error": "quote_not_found"}
            if quote["expires_at"] <= now:
                return "quote_expired", {"error": "quote_expired"}
            if context["quote_id"] != quote_id or context["revision"] != quote["revision"]:
                return "quote_superseded", {"error": "quote_superseded"}
            if db.execute("SELECT 1 FROM reservations WHERE conversation_id=? AND expires_at>?",
                          (conversation, now)).fetchone():
                return "active_reservation", {"error": "active_reservation"}
            variant = db.execute("SELECT * FROM variants WHERE sku=?", (quote["sku"],)).fetchone()
            quantity = self.availability(db, variant, now)
            if quantity is None:
                return "inventory_unavailable", {"error": "inventory_unavailable"}
            if quantity < 1:
                return "out_of_stock", {"error": "out_of_stock"}
            reservation_id = "R-" + secrets.token_hex(12)
            db.execute("INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?)",
                       (reservation_id, conversation, quote_id, quote["sku"], now, now + HOLD_SECONDS))
            row = db.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            return "ok", {"reservation": self.reservation(db, row, now), "created": True,
                          "revision": context["revision"]}

    def projection(self, conversation: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            now = self.clock()
            context = db.execute("SELECT * FROM shopping_contexts WHERE conversation_id=?", (conversation,)).fetchone()
            empty = {"revision": 0, "criteria": None, "products": [], "checked": None,
                     "quote": None, "reservation": None, "error": None}
            if context is None:
                return empty
            products = [self.product(db, p, now) for p in json.loads(context["result_ids"])]
            checked = json.loads(context["checked"]) if context["checked"] else None
            quote = None
            if context["quote_id"]:
                row = db.execute("SELECT * FROM quotes WHERE id=?", (context["quote_id"],)).fetchone()
                if row and row["expires_at"] > now:
                    quote = {k: row[k] for k in ("id", "sku", "revision", "item_price_cents", "shipping_cents",
                                                "destination", "requested_date", "delivery_method", "expires_at")}
                elif checked:
                    checked["quote_id"], checked["reason"] = None, "quote_expired"
            error = context["error"]
            if checked:
                variant = db.execute("SELECT * FROM variants WHERE sku=?", (checked["sku"],)).fetchone()
                checked["available_quantity"] = self.availability(db, variant, now)
                if checked["available_quantity"] is None or checked["available_quantity"] == 0:
                    quote, checked["quote_id"] = None, None
                    checked["reason"] = ("inventory_unavailable" if checked["available_quantity"] is None
                                         else "out_of_stock")
                    error = checked["reason"]
            hold = db.execute("SELECT * FROM reservations WHERE conversation_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
                              (conversation,)).fetchone()
            return {"revision": context["revision"], "criteria": json.loads(context["criteria"]) if context["criteria"] else None,
                    "products": products, "checked": checked, "quote": quote,
                    "reservation": self.reservation(db, hold, now) if hold else None, "error": error}
