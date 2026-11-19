import { describe, it, expect } from "vitest";
import {
  acceptSnapshot,
  availabilityLabel,
  currentView,
  remaining,
  productImage,
} from "./projection";
import type {
  SessionState,
  Product,
  Quote,
  Reservation,
  CheckResult,
} from "./types";
function snapshot(overrides: Partial<SessionState> = {}): SessionState {
  return {
    session: {
      id: "owned",
      scenario: "normal",
      status: "active",
      created_at: 100,
      expires_at: 2000,
      conversation_id: "provider",
    },
    revision: 1,
    criteria: null,
    products: [],
    checked: null,
    quote: null,
    reservation: null,
    error: null,
    events: [],
    last_retry: null,
    ...overrides,
  };
}
const product: Product = {
  id: "fil-01",
  name: "Fixture",
  description: "Synthetic test fixture",
  category: "shirt",
  occasion_tags: [],
  style_tags: [],
  fit_notes: "Relaxed",
  garment_measurements: { M: { chest_cm: 104, length_cm: 72 } },
  price_cents: 8000,
  image_path: "/products/fil-01.svg",
  variants: [{ sku: "sku", size: "M", colour: "ivori", available_quantity: 1 }],
};
const quote: Quote = {
  id: "quote",
  sku: "sku",
  revision: 1,
  item_price_cents: 8000,
  shipping_cents: 495,
  expires_at: 220,
  destination: "Barcelona",
  requested_date: "2026-11-20",
  delivery_method: "standard",
};
const reservation: Reservation = {
  id: "hold",
  quote_id: "quote",
  sku: "sku",
  product_id: "fil-01",
  size: "M",
  colour: "ivori",
  item_price_cents: 8000,
  shipping_cents: 495,
  destination: "Barcelona",
  requested_date: "2026-11-20",
  delivery_method: "standard",
  created_at: 100,
  expires_at: 700,
  status: "active",
};
const checked: CheckResult = {
  revision: 1,
  sku: "sku",
  product_id: "fil-01",
  size: "M",
  colour: "ivori",
  available_quantity: 1,
  price_cents: 8000,
  garment_measurements: { chest_cm: 104, length_cm: 72 },
  fit_notes: "Relaxed",
  destination: "Barcelona",
  requested_date: "2026-11-20",
  delivery_method: "standard",
  server_time: "2026-11-05T10:00:00+01:00",
  timezone: "Europe/Madrid",
  dispatch_date: "2026-11-05",
  estimated_arrival_date: "2026-11-09",
  shipping_cents: 495,
  eligible_by_requested_date: true,
  quote_id: "quote",
  quote_expires_at: 220,
  checked_at: 100,
  reason: null,
};
describe("authoritative shop projection", () => {
  it("begins empty and caps successful product cards at three", () => {
    expect(currentView(null, 100).products).toEqual([]);
    expect(
      currentView(snapshot({ products: Array(4).fill(product) }), 100).products,
    ).toHaveLength(3);
  });
  it("clears current products and quote on a failed search, without deleting real hold history", () => {
    const view = currentView(
      snapshot({
        products: [product],
        quote,
        reservation,
        error: "inventory_unavailable",
      }),
      200,
    );
    expect(view.products).toEqual([]);
    expect(view.quote).toBeNull();
    expect(view.reservation?.id).toBe("hold");
  });
  it("expires a quote independently of its existing ten-minute reservation", () => {
    const view = currentView(snapshot({ checked, quote, reservation }), 220);
    expect(view.quote).toBeNull();
    expect(view.checked).toBeNull();
    expect(view.reservation?.id).toBe("hold");
    expect(remaining(reservation.expires_at, 220)).toBe("8:00");
  });
  it("expires hold and session projections at their exact boundaries", () => {
    expect(currentView(snapshot({ reservation }), 700).reservation).toBeNull();
    const view = currentView(
      snapshot({ products: [product], quote, reservation }),
      2000,
    );
    expect(view.products).toEqual([]);
    expect(view.expired).toBe(true);
    expect(view.reservation).toBeNull();
    expect(remaining(700, 701)).toBe("0:00");
  });
  it("rejects late prior-session and older-search snapshots", () => {
    const current = snapshot({ revision: 4, products: [] });
    expect(
      acceptSnapshot(
        current,
        snapshot({ revision: 3, products: [product] }),
        "owned",
      ),
    ).toBe(current);
    const other = snapshot();
    other.session!.id = "previous";
    expect(acceptSnapshot(current, other, "owned")).toBe(current);
  });
  it("accepts no-match and equal-revision refreshed stock without reviving previous choices", () => {
    const current = snapshot({ products: [product] });
    const noMatch = snapshot({
      revision: 2,
      products: [],
      criteria: { size: "L" },
    });
    expect(acceptSnapshot(current, noMatch, "owned")).toBe(noMatch);
    const fresh = snapshot({
      products: [
        {
          ...product,
          variants: [{ ...product.variants[0], available_quantity: 0 }],
        },
      ],
    });
    expect(acceptSnapshot(current, fresh, "owned")).toBe(fresh);
  });
  it("renders only allowlisted original local product paths", () => {
    expect(productImage("/products/fil-08.svg")).toBe("/products/fil-08.svg");
    for (const path of [
      "https://example.test/pixel",
      "/products/../secret",
      "/products/fil-99.svg",
    ])
      expect(productImage(path)).toBeUndefined();
  });
});

it.each([null, 0])(
  "suppresses an existing valid quote when fresh stock is %s",
  (quantity) => {
    const view = currentView(
      snapshot({
        checked: { ...checked, available_quantity: quantity },
        quote,
      }),
      200,
    );
    expect(view.checked?.available_quantity).toBe(quantity);
    expect(view.quote).toBeNull();
    expect(availabilityLabel(quantity)).toBe(
      quantity === null ? "Estoc no confirmat" : "Sense estoc",
    );
  },
);
it("shows retry evidence only for the current live reservation", () => {
  const oldRetry = {
    reservation: { ...reservation, id: "previous-hold" },
    created: false,
    revision: 1,
  };
  expect(
    currentView(snapshot({ reservation, last_retry: oldRetry }), 200).lastRetry,
  ).toBeNull();
  const actual = { reservation, created: false, revision: 1 };
  expect(
    currentView(snapshot({ reservation, last_retry: actual }), 200).lastRetry,
  ).toBe(actual);
  expect(
    currentView(snapshot({ reservation, last_retry: actual }), 700).lastRetry,
  ).toBeNull();
});
