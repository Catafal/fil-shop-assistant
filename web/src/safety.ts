import { localeCode, type Locale } from "./localization";
export const euro = (cents: number, locale: Locale = "en") =>
  new Intl.NumberFormat(localeCode[locale], {
    style: "currency",
    currency: "EUR",
  }).format(cents / 100);
export const date = (value: string, locale: Locale = "en") =>
  new Intl.DateTimeFormat(localeCode[locale], {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(value + "T12:00:00Z"));
export const clock = (value: number, locale: Locale = "en") =>
  new Intl.DateTimeFormat(localeCode[locale], {
    timeZone: "Europe/Madrid",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value * 1000));
const messages: Record<string, string> = {
  access_required: "Introdueix el codi d’accés per obrir la demostració.",
  origin_denied:
    "Aquest origen no està autoritzat. Obre l’adreça configurada per a la demostració.",
  local_access_only:
    "Aquesta demostració només està disponible des de l’ordinador local.",
  session_active:
    "Ja hi ha una sessió oberta. Tanca-la abans de començar-ne una altra.",
  rate_limited:
    "Hem arribat al límit d’intents. Espera uns minuts abans de tornar-ho a provar.",
  session_expired: "La sessió ha caducat. Tanca-la i inicia una conversa nova.",
  session_required: "La sessió ha caducat. Tanca-la i inicia una conversa nova.",
  provider_unavailable:
    "No podem connectar amb el servei de veu. Torna-ho a provar més tard.",
  not_configured: "El servei de veu encara no està configurat.",
  retry_unavailable: "No hi ha cap reserva vigent que es pugui repetir.",
  inventory_unavailable:
    "L’inventari no està disponible ara. No podem confirmar cap peça ni reserva.",
  quote_expired:
    "L’estimació ha caducat. Demana a l’Ona que comprovi de nou la variant i l’enviament.",
  reservation_expired:
    "La reserva ha caducat. Un reintent no crea cap reserva nova.",
  invalid_access_code: "El codi d’accés no és correcte.",
};
export class ApiError extends Error {
  constructor(public code: string) {
    super(
      messages[code] ?? "No hem pogut completar l’acció. Torna-ho a provar.",
    );
  }
}
export async function api<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/demo" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: body == null ? undefined : { "Content-Type": "application/json" },
    body: body == null ? undefined : JSON.stringify(body),
    signal,
  });
  const data = await response
    .json()
    .catch(() => ({ error: "invalid_response" }));
  if (!response.ok)
    throw new ApiError(
      typeof data.error === "string" ? data.error : "unavailable",
    );
  return data as T;
}
export function displayError(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "No hi ha connexió amb la demostració. Comprova el servei i torna-ho a provar.";
}
