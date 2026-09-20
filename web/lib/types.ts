// Hand-written TypeScript types mirroring docs/schemas/play.schema.json,
// docs/schemas/gap.schema.json, docs/schemas/chat_envelope.schema.json and
// docs/schemas/vision_intake.schema.json. Keep field names identical to the schemas.

// ---------- play.schema.json ----------

export type Objective =
  | "clear_online_sellby"
  | "clear_expiry"
  | "prevent_stockout"
  | "rebalance"
  | "revive_slow_mover";

export type DeadlineType = "online_sellby" | "expiry" | "lead_time";

export type Mechanic =
  | "bundle"
  | "usual_order_addon"
  | "substitution"
  | "preorder"
  | "subscription_nudge"
  | "coupon"
  | "outlet_markdown"
  | "transfer_plus_nudge";

export type Channel = "web_chat" | "app_push" | "outlet";

export type GuardrailRule =
  | "margin_floor"
  | "frequency_cap"
  | "consent_required"
  | "sellby_disclosure"
  | "subscription_protect"
  | "no_cannibalise_stockout"
  | "holdout_required"
  | "cite_or_drop";

export type CitationType = "gap" | "estimator" | "outcome" | "policy" | "forecast" | "stock";

export type PlayStatus =
  | "proposed"
  | "approved"
  | "modified"
  | "rejected"
  | "running"
  | "measured"
  | "unmeasured";

export interface PlayTarget {
  sku: string;
  node_ids: string[];
  batch_ids: string[];
  units: number;
  deadline_date: string;
  deadline_type: DeadlineType;
}

export interface MechanicParams {
  discount_pct?: number;
  bundle_sku?: string;
  bundle_price?: number;
  transfer_to_node?: string;
  transfer_units?: number;
  preorder_eta_date?: string;
  markdown_pct?: number;
}

export interface AudienceFilters {
  min_affinity?: number;
  recency_days?: number;
  node_radius_km?: number;
}

export interface Audience {
  segment_ids: string[];
  filters: AudienceFilters;
  purpose: "marketing";
  size_before_consent: number;
  size_after_consent: number;
}

export interface PlayWindow {
  start: string;
  end: string;
}

export interface CopyVariant {
  segment_id: string;
  language: string;
  text: string;
  disclosure_included: boolean;
}

export interface PlayCopy {
  language_set: string[];
  variants: CopyVariant[];
  copy_status: "pending" | "generated" | "validated" | "rejected";
}

export interface ExpectedOutcome {
  units: number;
  margin_inr: number;
  waste_avoided_inr: number;
  discount_cost_inr: number;
  ci_low: number;
  ci_high: number;
  prior_n: number;
  measured_n: number;
  estimator_version: string;
}

export interface Counterfactuals {
  do_nothing_inr: number;
  blanket_markdown_inr: number;
  blanket_markdown_pct: number;
}

export interface Holdout {
  fraction: number;
  seed: string;
  min_treated_n: number;
}

export interface Guardrail {
  rule: GuardrailRule;
  passed: boolean;
  detail: string;
}

export interface Citation {
  type: CitationType;
  ref: string;
}

export interface Alternative {
  mechanic: string;
  mechanic_params: Record<string, unknown>;
  expected_units: number;
  expected_margin_inr: number;
  rejected_because: string;
}

export interface PlayEdit {
  field: string;
  from: unknown;
  to: unknown;
  at: string;
}

export interface PlayCost {
  plan_cost_inr?: number;
  conversation_budget_inr?: number;
  pct_of_rupees_at_stake?: number;
}

export interface Play {
  play_id: string;
  gap_id: string;
  tenant_id?: string;
  created_at: string;
  objective: Objective;
  target: PlayTarget;
  mechanic: Mechanic;
  mechanic_params: MechanicParams;
  audience: Audience;
  channel: Channel;
  window: PlayWindow;
  copy: PlayCopy;
  expected_outcome: ExpectedOutcome;
  counterfactuals: Counterfactuals;
  holdout: Holdout;
  guardrails: Guardrail[];
  rationale: string;
  citations: Citation[];
  alternatives: Alternative[];
  policy_version: string;
  trace_ref: string;
  status: PlayStatus;
  approved_by?: string;
  approved_at?: string;
  edits?: PlayEdit[];
  cost?: PlayCost;
}

// ---------- gap.schema.json ----------

export type GapType =
  | "online_sellby_breach"
  | "expiry_writeoff"
  | "stockout_risk"
  | "rebalance"
  | "slow_mover"
  | "unmet_demand"
  | "assortment_gap";

export interface GapEvidence {
  on_hand: number;
  projected_sellthrough: number;
  forecast_run_id: string;
  sellby_rule: string;
  inbound?: number;
  unit_cost?: number;
  margin_per_unit?: number;
  expiry_date?: string;
  sku_name?: string;
  // Real customer_requests rows behind this gap or corroborating it (stockout_risk, unmet_demand).
  requests_count?: number;
  distinct_customers?: number;
  // assortment_gap only (style_requests-derived; agents/stylist).
  requesting_customer_ids?: string[];
  supply_node_id?: string | null;
  garment_type?: string;
  colour_family?: string;
}

export interface Gap {
  gap_id: string;
  run_id?: string;
  type: GapType;
  sku: string;
  node_id: string;
  batch_id?: string | null;
  units_at_risk: number;
  deadline_date: string;
  deadline_type: DeadlineType;
  rupees_at_stake: number;
  evidence: GapEvidence;
}

// ---------- chat_envelope.schema.json ----------

export type ChatRole = "customer" | "agent" | "system";

export interface ChatButton {
  id: string;
  label: string; // <= 20 chars
}

export interface ChatListRow {
  id: string;
  title: string; // <= 24 chars
  desc?: string; // <= 72 chars
}

export interface ChatList {
  title: string; // <= 60 chars
  rows: ChatListRow[]; // <= 10
}

export interface ChatCitation {
  type: "stock" | "play" | "forecast";
  ref: string;
}

export interface ChatToolCall {
  name: string;
  args?: Record<string, unknown>;
  result_ref?: string;
}

export interface ChatEnvelope {
  session_id: string; // ^[A-Za-z0-9_-]+:(web|whatsapp)$
  message_id?: string;
  role: ChatRole;
  text: string; // <= 4096
  language?: string;
  buttons?: ChatButton[]; // <= 3
  list?: ChatList;
  citations?: ChatCitation[];
  tool_calls?: ChatToolCall[];
  latency_ms?: number;
  ts?: string;
}

// ---------- vision_intake.schema.json ----------

export interface VisionRow {
  sku_guess: string;
  sku_confidence: number;
  best_before_date: string | null;
  date_confidence: number;
  facings_count: number;
  count_confidence: number;
  crop_ref?: string;
  needs_confirmation?: boolean;
  confirmation_question?: string;
}

export interface VisionIntakeResult {
  photo_ref: string;
  node_id: string;
  model_id: string;
  pass?: "single" | "two_pass";
  rows: VisionRow[];
}

// ---------- API shapes (docs/openapi.yaml) ----------

export type Source = "live" | "recorded";

export interface HealthCheck {
  ok: boolean;
  checked_at: string;
  latency_ms?: number;
  detail?: string;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "down";
  version?: string;
  checks: Record<string, HealthCheck>; // bigquery, firestore, vertex, sessions
  tenant?: { tenant_id: string; name: string; skus: number; nodes: number; customers: number };
  last_sense_run_at?: string;
  last_sense_run_minutes?: number;
}

export interface ForecastPoint {
  date: string;
  baseline_p50: number;
  play_p50: number;
  p10?: number;
  p90?: number;
}

export interface Forecast {
  run_id: string;
  model: string; // e.g. "ML.FORECAST"
  latency_ms: number;
  series: ForecastPoint[];
  writeoff_before_inr: number;
  writeoff_after_inr: number;
  play_window: PlayWindow;
}

export interface ApproveRequest {
  play_id: string;
  holdout_fraction?: number;
  rationale?: string;
  edits?: PlayEdit[];
  approved_by?: string;
}

export interface ApproveResponse {
  play_id: string;
  status: PlayStatus;
  assignment: { treated_n: number; holdout_n: number; seed: string };
  forecast: Forecast;
  source: Source;
  note?: string;
}

export interface RerunRequest {
  gap_id: string;
  policy_text: string;
  policy_version?: string;
}

export interface RerunResponse {
  run_id: string;
  play: Play;
  policy_version: string;
  source: Source;
}

export interface TraceEvent {
  seq: number;
  run_id: string;
  invocation_id: string;
  author: string;
  timestamp: string;
  ts_offset_ms: number;
  text?: string;
  function_call?: { name: string; args?: Record<string, unknown> };
  function_response?: { name: string; response?: Record<string, unknown> };
  level?: "info" | "warn" | "error" | "ok";
}

export interface EventsResponse {
  run_id: string;
  recorded_at?: string;
  events: TraceEvent[];
}

export interface ChatRequest {
  session_id: string;
  text: string;
  customer_id?: string;
  language?: string;
  specialist?: "customer" | "stylist";
  image_data_url?: string;
  photo_ref?: string;
  image_kind?: "garment" | "selfie";
}

export interface ResetResponse {
  ok: boolean;
  namespace: string;
  restored_from?: string;
}

export interface MeasureResponse {
  plays: number;
  measured: number;
  unmeasured: number;
  // Plays whose assignment made a lift computation impossible this run (e.g. zero holdout by
  // chance on a small audience) -- left out of play_outcomes entirely rather than crashing
  // measurement for every other play.
  skipped?: string[];
  computed_at: string;
}

export interface CaptureRequest {
  node_id: string;
  photo_ref?: string;
  image_data_url?: string;
}

export interface OutcomeArm {
  customers: number;
  responders: number;
  units: number;
  revenue_inr: number;
  margin_inr: number;
  discount_cost_inr: number;
}

export interface Outcome {
  play_id: string;
  sku: string;
  node_id: string;
  mechanic: Mechanic;
  status: "measured" | "unmeasured";
  measured_at?: string;
  min_treated_n: number;
  treated: OutcomeArm;
  holdout: OutcomeArm;
  lift?: number | null;
  ci_low?: number | null;
  ci_high?: number | null;
  waste_avoided_inr?: number | null;
  margin_per_discount_rupee?: number | null; // the CEO number; null when no discount was given
  looker_url?: string;
  data_label: "REAL PILOT" | "SYNTHETIC";
}

export interface ExecutionStep {
  id: string;
  text: string;
}

export interface ExecutionRequest {
  play_id: string;
  node_id: string;
  steps_done: string[];
  evidence_photo_data_url?: string;
  note?: string;
}

export interface ExecutionResponse {
  ok: boolean;
  execution_id: string;
  recorded_at: string;
}

export interface PolicyDoc {
  policy_version: string;
  text: string;
  updated_at: string;
}


export interface DemoCustomer {
  customer_id: string;
  display_name: string;
  home_node_id: string;
  language: string;
  role: "sample" | "holdout";
  note: string;
}

export interface StyleTrend {
  tenant_id: string;
  run_id: string;
  node_id: string;
  window_days: number;
  garment_type: string | null;
  colour_family: string | null;
  occasion: string | null;
  asks: number;
  distinct_customers: number;
  unfulfilled_asks: number;
  computed_at: string;
  data_label: "SYNTHETIC";
}

export interface TrendsRecomputeResponse {
  rows: number;
  window_days: number;
  computed_at: string;
}
