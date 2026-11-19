export type Config = {
  configured: boolean;
  access_required: boolean;
  brand: string;
  scenarios: { id: string; label: string }[];
};
export type Product = {
  id: string;
  name: string;
  description: string;
  category: string;
  occasion_tags: string[];
  style_tags: string[];
  fit_notes: string;
  garment_measurements: Record<string, { chest_cm: number; length_cm: number }>;
  price_cents: number;
  image_path: string;
  variants: {
    sku: string;
    size: string;
    colour: string;
    available_quantity: number | null;
    inventory_status?: "available" | "unavailable";
  }[];
};
export type SearchCriteria = {
  category?: string | null;
  occasion?: string | null;
  max_price_cents?: number | null;
  colour?: string | null;
  size?: string | null;
};
export type CheckResult = {
  revision: number;
  sku: string;
  product_id: string;
  size: string;
  colour: string;
  available_quantity: number | null;
  price_cents: number;
  garment_measurements: { chest_cm: number; length_cm: number };
  fit_notes: string;
  destination: string;
  requested_date: string;
  delivery_method: "standard" | "express";
  server_time: string;
  timezone: string;
  dispatch_date: string | null;
  estimated_arrival_date: string | null;
  shipping_cents: number | null;
  eligible_by_requested_date: boolean | null;
  quote_id: string | null;
  quote_expires_at: number | null;
  checked_at: number;
  reason: string | null;
};
export type Quote = {
  id: string;
  sku: string;
  revision: number;
  item_price_cents: number;
  shipping_cents: number;
  expires_at: number;
  destination: string;
  requested_date: string;
  delivery_method: "standard" | "express";
};
export type Reservation = {
  product_name?: string;
  id: string;
  quote_id: string;
  sku: string;
  product_id: string;
  size: string;
  colour: string;
  item_price_cents: number;
  shipping_cents: number;
  destination: string;
  requested_date: string;
  delivery_method: "standard" | "express";
  created_at: number;
  expires_at: number;
  status: "active" | "expired";
};
export type ReserveResult = {
  reservation: Reservation;
  created: boolean;
  revision: number;
};
export type SessionState = {
  session: null | {
    id: string;
    scenario: string;
    status: "active" | "ended";
    created_at: number;
    expires_at: number;
    conversation_id: string;
  };
  revision: number;
  criteria: SearchCriteria | null;
  products: Product[];
  checked: CheckResult | null;
  quote: Quote | null;
  reservation: Reservation | null;
  error: string | null;
  events: {
    sequence: number;
    at: number;
    kind: string;
    status: number;
    payload: Record<string, unknown>;
  }[];
  last_retry: ReserveResult | null;
};
export type SessionToken = {
  id: string;
  conversation_token: string;
  conversation_id: string;
  expires_at: number;
};
export type GuidedScenario = "normal" | "inventory-outage";
export type GuidedAction = "change-colour" | "check" | "reserve" | "decline" | "retry";
export type GuidedState = {
  stage: "initial" | "revised" | "quoted" | "held" | "declined" | "outage";
  view: SessionState & { session: NonNullable<SessionState["session"]> };
};
export type TranscriptLine = {
  id: string;
  role: "user" | "agent";
  message: string;
};
