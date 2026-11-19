import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ConversationProvider } from "@elevenlabs/react";
import App from "./App";
import { localizeTree, translate, metadata, type Locale } from "./localization";
import { euro, date, clock } from "./safety";
import { ReservationCard } from "./ReservationCard";
import type { Reservation } from "./types";
import catalogue from "../../src/fil_shop/catalogue.py?raw";
it("renders the initial site in English with all three locale choices", () => {
  const html = renderToStaticMarkup(
    <ConversationProvider>
      <App />
    </ConversationProvider>,
  );
  expect(html).toContain("Find something");
  expect(html).toContain("like you.");
  expect(html).toContain("FICTIONAL SHOP");
  expect(html).toContain('value="en" selected');
  expect(html).toContain("Català");
  expect(html).toContain("Español");
  expect(html).not.toContain("Troba allò");
  expect(html).toContain("Interface language");
});
it("translates presentation attributes without altering spoken text, identifiers or callbacks", () => {
  let count = 0;
  const click = () => {
    count++;
  };
  const element = (
    <section>
      <button title="Provar altaveu" onClick={click}>
        Provar altaveu
      </button>
      <p data-untranslated>Sense estoc</p>
      <code>FIL01-M-NAVY</code>
      <input value="navy" readOnly aria-label="Nivell d’entrada" />
    </section>
  );
  const html = renderToStaticMarkup(localizeTree(element, "en"));
  expect(html).toContain('title="Test speaker"');
  expect(html).toContain(">Sense estoc</p>");
  expect(html).toContain("FIL01-M-NAVY");
  expect(html).toContain('value="navy"');
  expect(html).toContain('aria-label="Input level"');
  expect(count).toBe(0);
});
it("covers every current catalogue name, description and fit note by exact source; unknown facts stay original", () => {
  const sourceFacts = [
    ...catalogue.matchAll(/"(?:name|description|fit_notes)": "([^"]+)"/g),
  ].map((match) => match[1]);
  expect(sourceFacts).toHaveLength(24);
  for (const fact of sourceFacts) {
    expect(translate(fact, "en")).not.toBe(fact);
    expect(translate(fact, "ca")).toBe(fact);
    expect(translate(fact, "es").length).toBeGreaterThan(3);
  }
  expect(translate("A new silk coat with an unreviewed fit note.", "es")).toBe(
    "A new silk coat with an unreviewed fit note.",
  );
  expect(translate("Camisa lleugera de lli i cotó.", "en")).toBe(
    "Lightweight linen and cotton shirt.",
  );
  expect(translate("Top recte de lyocell amb coll rodó.", "es")).toBe(
    "Top recto de lyocell con cuello redondo.",
  );
});
it.each(["en", "ca", "es"] as Locale[])(
  "preserves persisted hold facts, amounts and stock distinctions in %s",
  (locale) => {
    const hold: Reservation = {
      id: "hold",
      quote_id: "quote",
      sku: "FIL01-M-NAVY",
      product_id: "fil-01",
      product_name: "Camisa Brisa",
      size: "M",
      colour: "navy",
      item_price_cents: 5900,
      shipping_cents: 495,
      destination: "Barcelona",
      requested_date: "2026-11-20",
      delivery_method: "standard",
      created_at: 100,
      expires_at: 700,
      status: "active",
    };
    const html = renderToStaticMarkup(
      <ReservationCard reservation={hold} active now={220} locale={locale} />,
    );
    expect(html).toContain(translate("Camisa Brisa", locale));
    expect(html).toContain(translate("navy", locale));
    expect(html).toContain("8:00");
    expect(html).toContain(euro(5900, locale));
    expect(html).toContain(euro(495, locale));
    expect(translate("Estoc no confirmat", locale)).not.toBe(
      translate("Sense estoc", locale),
    );
    expect(date("2026-11-20", locale)).toContain("20");
    expect(metadata[locale].description.length).toBeGreaterThan(30);
  },
);
it("formats a calendar day without timezone drift and uses Madrid for event time", () => {
  expect(date("2026-11-20", "en")).toBe("20 Nov");
  expect(euro(5900, "en")).toBe("€59.00");
  expect(euro(5900, "ca")).toContain("59,00");
  expect(clock(Date.parse("2026-11-20T23:30:00Z") / 1000, "en")).toBe(
    "00:30:00",
  );
});
