import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ReservationCard } from "./ReservationCard";
import type { Reservation } from "./types";
const hold: Reservation = {
  id: "hold-1",
  quote_id: "old-quote",
  sku: "held-sku",
  product_id: "fil-02",
  product_name: "Peça reservada original",
  size: "M",
  colour: "blau",
  item_price_cents: 8900,
  shipping_cents: 495,
  destination: "Barcelona",
  requested_date: "2026-11-20",
  delivery_method: "standard",
  created_at: 100,
  expires_at: 700,
  status: "active",
};
it("renders the persisted hold identity and prices without current product cards or quote", () => {
  const html = renderToStaticMarkup(
    <ReservationCard reservation={hold} active now={220} />,
  );
  for (const fact of [
    "Peça reservada original",
    "blau",
    "M",
    "89.00",
    "4.95",
    "8:00",
  ])
    expect(html).toContain(fact);
});
it("keeps the stable persisted product ID when the optional name is unavailable", () => {
  const html = renderToStaticMarkup(
    <ReservationCard
      reservation={{ ...hold, product_name: undefined }}
      active={false}
      now={701}
    />,
  );
  expect(html).toContain("fil-02");
  expect(html).toContain("89.00");
  expect(html).toContain("4.95");
  expect(html).toContain("0:00");
});
