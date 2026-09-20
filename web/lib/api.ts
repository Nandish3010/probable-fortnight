// Taal API client. Talks to the real backend (docs/openapi.yaml) unless
// NEXT_PUBLIC_TAAL_MOCK=1, in which case every route is served from the
// static fixtures under web/mocks/*.json (bundled at build time).
import type {
  ApproveRequest,
  DemoCustomer,
  ApproveResponse,
  CaptureRequest,
  ChatEnvelope,
  ChatRequest,
  EventsResponse,
  ExecutionRequest,
  ExecutionResponse,
  Gap,
  HealthResponse,
  MeasureResponse,
  Outcome,
  Play,
  PolicyDoc,
  RerunRequest,
  RerunResponse,
  ResetResponse,
  StyleTrend,
  TrendsRecomputeResponse,
  VisionIntakeResult,
} from "./types";
import { getVisitorId } from "./visitor";

import mockHealth from "../mocks/health.json";
import mockGaps from "../mocks/gaps.json";
import mockPlays from "../mocks/plays.json";
import mockApprove from "../mocks/approve.json";
import mockEvents from "../mocks/events.json";
import mockPolicy from "../mocks/policy.json";
import mockRerun from "../mocks/rerun.json";
import mockCapture from "../mocks/capture.json";
import mockExecution from "../mocks/execution.json";
import mockOutcomes from "../mocks/outcomes.json";
import mockCustomersDemo from "../mocks/customers_demo.json";
import mockChat from "../mocks/chat.json";
import mockStylistChat from "../mocks/stylist_chat.json";
import mockTrends from "../mocks/trends.json";

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_TAAL_MOCK === "1";
}

function apiBase(): string {
  // Strip a trailing slash so `${apiBase()}${path}` (path always starts with "/") never
  // produces a double slash, which 404s against FastAPI's exact route paths.
  const base = process.env.NEXT_PUBLIC_TAAL_API_URL ?? "http://localhost:8080";
  return base.replace(/\/+$/, "");
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Taal-Visitor", getVisitorId());
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

// ---------- health ----------

export async function getHealth(): Promise<HealthResponse> {
  if (isMockMode()) {
    await delay(120);
    return mockHealth as HealthResponse;
  }
  return request<HealthResponse>("/health");
}

// ---------- gaps ----------

export async function getGaps(params?: { node_id?: string; limit?: number }): Promise<Gap[]> {
  if (isMockMode()) {
    await delay(150);
    const all = mockGaps as Gap[];
    if (params?.node_id) {
      return all
        .filter((g) => g.node_id === params.node_id)
        .sort((a, b) => b.rupees_at_stake - a.rupees_at_stake);
    }
    return [...all].sort((a, b) => b.rupees_at_stake - a.rupees_at_stake);
  }
  const q = new URLSearchParams();
  if (params?.node_id) q.set("node_id", params.node_id);
  q.set("limit", String(params?.limit ?? 1000));
  return request<Gap[]>(`/gaps?${q.toString()}`);
}

// ---------- plays ----------

export async function getPlays(params?: { gap_id?: string }): Promise<Play[]> {
  if (isMockMode()) {
    await delay(150);
    const all = mockPlays as unknown as Play[];
    if (params?.gap_id) return all.filter((p) => p.gap_id === params.gap_id);
    return all;
  }
  const qs = params?.gap_id ? `?gap_id=${encodeURIComponent(params.gap_id)}` : "";
  return request<Play[]>(`/plays${qs}`);
}

// ---------- approve ----------

export async function approve(req: ApproveRequest): Promise<ApproveResponse> {
  if (isMockMode()) {
    await delay(1100);
    const base = mockApprove as unknown as ApproveResponse;
    return { ...base, play_id: req.play_id };
  }
  return request<ApproveResponse>("/approve", { method: "POST", body: JSON.stringify(req) });
}

// ---------- rerun (policy change -> re-plan) ----------

export async function rerun(req: RerunRequest): Promise<RerunResponse> {
  if (isMockMode()) {
    await delay(900);
    const base = mockRerun as unknown as RerunResponse;
    return {
      ...base,
      play: { ...base.play, gap_id: req.gap_id, rationale: `${base.play.rationale}` },
    };
  }
  return request<RerunResponse>("/rerun", { method: "POST", body: JSON.stringify(req) });
}

// ---------- policy ----------

export async function getPolicy(): Promise<PolicyDoc> {
  if (isMockMode()) {
    await delay(100);
    return mockPolicy as unknown as PolicyDoc;
  }
  return request<PolicyDoc>("/policy");
}

// ---------- events / trace ----------

export async function getEvents(runId: string): Promise<EventsResponse> {
  if (isMockMode()) {
    await delay(150);
    return mockEvents as unknown as EventsResponse;
  }
  return request<EventsResponse>(`/events/${encodeURIComponent(runId)}`);
}

// ---------- capture (phone view) ----------

export async function capture(req: CaptureRequest): Promise<VisionIntakeResult> {
  if (isMockMode()) {
    await delay(1400);
    const base = mockCapture as unknown as VisionIntakeResult;
    return { ...base, node_id: req.node_id, photo_ref: req.photo_ref ?? base.photo_ref };
  }
  return request<VisionIntakeResult>("/capture", { method: "POST", body: JSON.stringify(req) });
}

export interface CaptureConfirmResponse {
  ok: boolean;
  written: number;
}

// Confirmed rows -> inventory_batches (source=photo). Unconfirmed low-confidence rows are skipped server-side.
export async function captureConfirm(req: { node_id: string; photo_ref: string; rows: unknown[] }): Promise<CaptureConfirmResponse> {
  if (isMockMode()) {
    await delay(200);
    return { ok: true, written: req.rows.length };
  }
  return request<CaptureConfirmResponse>("/capture/confirm", { method: "POST", body: JSON.stringify(req) });
}

// ---------- execution ----------

export async function execution(req: ExecutionRequest): Promise<ExecutionResponse> {
  if (isMockMode()) {
    await delay(300);
    return mockExecution as ExecutionResponse;
  }
  return request<ExecutionResponse>("/execution", { method: "POST", body: JSON.stringify(req) });
}

// ---------- outcomes ----------

export async function getDemoCustomers(playId = "play_chips_ds07_v1"): Promise<DemoCustomer[]> {
  if (isMockMode()) {
    await delay(150);
    return mockCustomersDemo as unknown as DemoCustomer[];
  }
  return request<DemoCustomer[]>(`/customers/demo?play_id=${encodeURIComponent(playId)}`);
}

export async function getOutcomes(): Promise<Outcome[]> {
  if (isMockMode()) {
    await delay(150);
    return mockOutcomes as unknown as Outcome[];
  }
  return request<Outcome[]>("/outcomes");
}

// Joins play_assignments to order_lines for every approved play and writes play_outcomes; the
// only thing that ever populates /outcomes. Nothing calls this automatically -- a fresh visitor
// sandbox has an approved play with zero outcomes until Measure runs at least once.
export async function postMeasure(): Promise<MeasureResponse> {
  if (isMockMode()) {
    await delay(600);
    const rows = mockOutcomes as unknown as Outcome[];
    return {
      plays: rows.length,
      measured: rows.filter((r) => r.status === "measured").length,
      unmeasured: rows.filter((r) => r.status !== "measured").length,
      computed_at: new Date().toISOString(),
    };
  }
  return request<MeasureResponse>("/measure", { method: "POST" });
}

// ---------- reset ----------

export async function resetDemoData(): Promise<ResetResponse> {
  if (isMockMode()) {
    await delay(300);
    return { ok: true, namespace: getVisitorId(), restored_from: "snapshot:mock" };
  }
  return request<ResetResponse>("/reset", { method: "POST" });
}

// ---------- chat ----------

function pickMockScenario(req: ChatRequest): ChatEnvelope[] {
  const t = req.text.toLowerCase();
  if (req.specialist === "stylist") {
    const chat = mockStylistChat as unknown as Record<string, ChatEnvelope[]>;
    if (req.image_data_url && req.image_kind === "selfie") return chat.greeting; // no selfie mock scenario recorded yet
    if (req.image_data_url) return chat.photo;
    if (t.includes("stop")) return chat.stop;
    if (t.startsWith("add:") || t.startsWith("add ") || t.startsWith("order")) return chat.default;
    if (t.startsWith("item:")) return chat.item;
    if (t.includes("wedding") || t.includes("festive") || t.includes("office")) return chat.occasion;
    if (t.includes("navy")) return chat.search_navy;
    if (t.includes("goes with") || t.includes("pair") || t.includes("mustard")) return chat.pair_kurta;
    if (t.includes("hi") || t.includes("hello") || !t) return chat.greeting;
    return chat.unknown;
  }
  const chat = mockChat as unknown as Record<string, ChatEnvelope[]>;
  if (t.includes("stop")) return chat.stop;
  if (t.startsWith("add:") || t.startsWith("add ") || t.startsWith("order")) return chat.order;
  if (t.includes("cola") || t.includes("zero")) return chat.cola_zero;
  if (t.includes("what") || t.includes("menu") || t.includes("browse")) return chat.browse;
  if (t.includes("chips")) return chat.chips;
  if (t.includes("offer") || t.includes("hi") || t.includes("hello")) return chat.greeting;
  return chat.default;
}

// Streams chat envelopes one at a time via a callback, mirroring the SSE
// framing of the real endpoint (`data: <ChatEnvelope JSON>` per line).
export async function sendChat(
  req: ChatRequest,
  onEnvelope: (envelope: ChatEnvelope, latencyMs: number) => void,
): Promise<void> {
  if (isMockMode()) {
    const envelopes = pickMockScenario(req);
    for (const envelope of envelopes) {
      const latency = envelope.latency_ms ?? 900;
      await delay(Math.min(latency, 1600));
      onEnvelope({ ...envelope, session_id: req.session_id, ts: new Date().toISOString() }, latency);
    }
    return;
  }

  const started = Date.now();
  const res = await fetch(`${apiBase()}/chat`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Taal-Visitor": getVisitorId(),
    },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`/chat -> ${res.status}`);

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const envelopes = (await res.json()) as ChatEnvelope[];
    for (const envelope of envelopes) {
      onEnvelope(envelope, envelope.latency_ms ?? Date.now() - started);
    }
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const payload = trimmed.slice(5).trim();
      if (!payload) continue;
      try {
        const envelope = JSON.parse(payload) as ChatEnvelope;
        onEnvelope(envelope, envelope.latency_ms ?? Date.now() - started);
      } catch {
        // Ignore malformed SSE frames rather than breaking the stream.
      }
    }
  }
}

// ---------- style trends ----------

export async function getTrends(params?: { node_id?: string }): Promise<StyleTrend[]> {
  if (isMockMode()) {
    await delay(150);
    const all = mockTrends as unknown as StyleTrend[];
    if (params?.node_id) return all.filter((t) => t.node_id === params.node_id);
    return all;
  }
  const q = params?.node_id ? `?node_id=${encodeURIComponent(params.node_id)}` : "";
  return request<StyleTrend[]>(`/trends${q}`);
}

export async function postTrendsRecompute(): Promise<TrendsRecomputeResponse> {
  if (isMockMode()) {
    await delay(400);
    const rows = mockTrends as unknown as StyleTrend[];
    return { rows: rows.length, window_days: rows[0]?.window_days ?? 30, computed_at: new Date().toISOString() };
  }
  return request<TrendsRecomputeResponse>("/trends/recompute", { method: "POST" });
}
