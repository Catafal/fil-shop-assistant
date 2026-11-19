import { localizeTree, type Locale } from "./localization";
import type { Reservation } from "./types";
import { euro as formatEuro } from "./safety";
import { remaining } from "./projection";

// A hold remains the same item even when the customer changes the current search.
export function ReservationCard({
  reservation,
  locale = "en",
  active,
  now,
}: {
  reservation: Reservation;
  locale?: Locale;
  active: boolean;
  now: number;
}) {
  const euro = (value: number) => formatEuro(value, locale);
  return localizeTree(
    <section
      className={"reservation " + (!active ? "expired" : "")}
      aria-live="polite"
    >
      <div>
        <p className="eyebrow">
          {active ? "UNA PEÇA, GUARDADA PER A TU" : "RESERVA FINALITZADA"}
        </p>
        <h3>
          {active
            ? "La teva reserva està feta."
            : "El temps de reserva ha acabat."}
        </h3>
        <p>
          <strong>{reservation.product_name || reservation.product_id}</strong>{" "}
          · {reservation.colour} / {reservation.size}
        </p>
        <p>
          Peça {euro(reservation.item_price_cents)} + enviament{" "}
          {euro(reservation.shipping_cents)}.
        </p>
        <p>Reserva de demostració, no una compra.</p>
      </div>
      <div className="reservation-clock">
        <span>{active ? remaining(reservation.expires_at, now) : "0:00"}</span>
        <small>{active ? "MINUTS RESTANTS" : "SENSE RETENCIÓ ACTIVA"}</small>
      </div>
    </section>,
    locale,
  );
}
