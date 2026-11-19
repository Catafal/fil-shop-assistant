import type { SessionState } from "./types";
// Arrival order is not authority: tool history can outlive the current search intent.
export function acceptSnapshot(
  current: SessionState | null,
  next: SessionState,
  expectedSession: string | null,
): SessionState | null {
  if (expectedSession && next.session && next.session.id !== expectedSession)
    return current;
  if (current?.session?.id === next.session?.id && current) {
    if (next.revision < current.revision) return current;
    const last = (state: SessionState) => state.events.at(-1)?.sequence ?? 0;
    if (next.revision === current.revision && last(next) < last(current))
      return current;
  }
  return next;
}
export function currentView(state: SessionState | null, now: number) {
  const expired = !!state?.session && state.session.expires_at <= now;
  const usable = !!state?.session && !expired && !state.error;
  const checked =
    usable && state.checked && state.checked.checked_at + 120 > now
      ? state.checked
      : null;
  const reservation =
    !expired &&
    state?.reservation &&
    state.reservation.expires_at > now &&
    state.reservation.status === "active"
      ? state.reservation
      : null;
  return {
    products: usable ? state.products.slice(0, 3) : [],
    checked,
    quote:
      usable &&
      state.quote &&
      state.quote.expires_at > now &&
      checked &&
      checked.available_quantity !== null &&
      checked.available_quantity > 0 &&
      checked.sku === state.quote.sku
        ? state.quote
        : null,
    reservation,
    lastRetry:
      reservation && state?.last_retry?.reservation.id === reservation.id
        ? state.last_retry
        : null,
    expired,
  };
}
export function availabilityLabel(quantity: number | null): string {
  return quantity === null
    ? "Estoc no confirmat"
    : quantity > 0
      ? `${quantity} disponibles`
      : "Sense estoc";
}
export function remaining(until: number, now: number): string {
  const seconds = Math.max(0, Math.ceil(until - now));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
export function productImage(path: string): string | undefined {
  return /^\/products\/fil-0[1-8]\.svg$/.test(path) ? path : undefined;
}
