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
  FeedbackForm,
  FeedbackSubmission,
  FeedbackSubmitResponse,
  FeedbackSummary,
  PriorUpdate,
  ExecutionResponse,
  Gap,
  HealthResponse,
  MeasureResponse,
  Outcome,
  Play,
  PolicyDoc,
  RerunAccepted,
  RerunRequest,
  RerunResult,
  RerunStatus,
  ResetResponse,
  TraceEvent,
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
import mockRerunEvents from "../mocks/rerun_events.json";
import mockCapture from "../mocks/capture.json";
import mockExecution from "../mocks/execution.json";
import mockOutcomes from "../mocks/outcomes.json";
import mockPriorUpdate from "../mocks/prior_update.json";
import mockCustomersDemo from "../mocks/customers_demo.json";
import mockChat from "../mocks/chat.json";
import mockFeedbackForm from "../mocks/feedback_form.json";
// The summary a zero-response store produces (summarize([]) output): mock mode never shows
// simulated feedback numbers, not even to a demo viewer.
import mockFeedbackSummary from "../mocks/feedback_summary.json";

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

// Thrown by request() on a non-ok response; `status` lets a caller (e.g. rerun() below, on 409)
// give a clearer message than the generic one this carries.
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
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
    throw new ApiError(`${path} -> ${res.status}`, res.status);
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
//
// POST /rerun is asynchronous (202 Accepted; the planner runs on a worker thread after the
// response lands -- a live Gemini call takes 20-45s). Follow the returned stream_url with
// streamRerun() for a live-updating trace, or poll status_url with getRerunStatus(); either
// resolves to the same RerunResult shape.

export async function rerun(req: RerunRequest): Promise<RerunAccepted> {
  if (isMockMode()) {
    await delay(300);
    const base = mockRerun as unknown as RerunResult;
    const runId = base.run_id;
    return {
      run_id: runId,
      status: "running",
      gap_id: req.gap_id,
      policy_version: req.policy_version || base.policy_version || "v2",
      backend: "stub",
      deadline_s: 8,
      stream_url: `/events/${runId}/stream`,
      status_url: `/rerun/${runId}`,
    };
  }
  try {
    return await request<RerunAccepted>("/rerun", { method: "POST", body: JSON.stringify(req) });
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      throw new Error("A re-plan is already running for this visitor. Wait for it to finish, then try again.");
    }
    throw e;
  }
}

// Every "message"/"data:" and "event:"/"data:" frame of an SSE body, in arrival order, ignoring
// blank lines and lines starting with ":" (a keepalive comment) -- the same framing
// harness/build_mocks.py's own `_parse_sse` reads back out of a recorded stream. `onFrame` fires
// once per frame with its event name ("message" when none was sent) and parsed JSON data.
async function consumeSseStream(res: Response, onFrame: (eventName: string, data: unknown) => void): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("SSE response has no body to read");
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName: string | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const rawLine of lines) {
      const line = rawLine.replace(/\r$/, "");
      if (!line || line.startsWith(":")) continue;
      if (line.startsWith("event:")) {
        eventName = line.slice("event:".length).trim();
        continue;
      }
      if (line.startsWith("data:")) {
        const payload = line.slice("data:".length).trim();
        if (payload) onFrame(eventName ?? "message", JSON.parse(payload));
        eventName = null;
      }
    }
  }
}

// Follows GET /events/{run_id}/stream for the visitor's own in-flight run (a plain fetch, not
// EventSource -- EventSource cannot send the X-Taal-Visitor header this endpoint requires):
// `onRecord` fires for each plain trace-record frame as it arrives, and the returned promise
// resolves with the terminal `event: done` frame's data once the run finishes. Throws if the
// stream closes without ever sending one (a dropped connection, not a clean finish).
export async function streamRerun(
  runId: string,
  onRecord: (record: TraceEvent) => void,
  signal?: AbortSignal,
): Promise<RerunResult> {
  if (isMockMode()) {
    const frames = mockRerunEvents as unknown as { event: string; data: unknown }[];
    let result: RerunResult | null = null;
    for (const frame of frames) {
      if (signal?.aborted) break;
      await delay(250); // keeps the streaming state visible for a couple of seconds, as in a real run
      if (frame.event === "done") {
        result = frame.data as RerunResult;
      } else {
        onRecord(frame.data as TraceEvent);
      }
    }
    return result ?? (mockRerun as unknown as RerunResult);
  }

  const res = await fetch(`${apiBase()}/events/${encodeURIComponent(runId)}/stream`, {
    credentials: "include",
    headers: { "X-Taal-Visitor": getVisitorId() },
    signal,
  });
  if (!res.ok) throw new ApiError(`/events/${runId}/stream -> ${res.status}`, res.status);

  let result: RerunResult | null = null;
  await consumeSseStream(res, (eventName, data) => {
    if (eventName === "done") {
      result = data as RerunResult;
    } else {
      onRecord(data as TraceEvent);
    }
  });

  if (!result) throw new Error(`/events/${runId}/stream ended without a "done" frame`);
  return result;
}

export async function getRerunStatus(runId: string): Promise<RerunStatus> {
  if (isMockMode()) {
    await delay(150);
    const result = mockRerun as unknown as RerunResult;
    const now = new Date().toISOString();
    return { run_id: runId, status: "done", started_at: now, finished_at: now, result };
  }
  return request<RerunStatus>(`/rerun/${encodeURIComponent(runId)}`);
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

export interface CaptureConfirmSkip {
  sku_guess: string;
  reason: "not confirmed" | "unknown SKU" | "no best_before_date";
}

export interface CaptureConfirmResponse {
  ok: boolean;
  written: number;
  batches: Record<string, unknown>[];
  skipped: CaptureConfirmSkip[];
  gaps_refreshed: number;
}

// Confirmed rows -> inventory_batches (source=photo). A row that needs but lacks confirmation,
// names an unknown SKU, or has no best_before_date is skipped with a reason in `skipped`, never
// silently dropped.
export async function captureConfirm(req: { node_id: string; photo_ref: string; rows: unknown[] }): Promise<CaptureConfirmResponse> {
  if (isMockMode()) {
    await delay(200);
    return { ok: true, written: req.rows.length, batches: [], skipped: [], gaps_refreshed: 0 };
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

// Built once with the tenant and served from the base data dir, so it is the same for every
// visitor and "Reset demo data" does not change it.
export async function getPriorUpdate(): Promise<PriorUpdate> {
  if (isMockMode()) {
    await delay(150);
    return mockPriorUpdate as unknown as PriorUpdate;
  }
  return request<PriorUpdate>("/outcomes/prior-update");
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

// ---------- practitioner feedback ----------
// The one real dataset, stored apart from the demo tenant. POST /feedback carries the per-device
// visitor id only as the rate-limit key: without it every phone behind Cloud Run's front end
// would share one bucket, and a link shared to a group could lock real respondents out. The id
// is never stored with a response.

export class FeedbackError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function getFeedbackForm(): Promise<FeedbackForm> {
  if (isMockMode()) {
    await delay(80);
    return mockFeedbackForm as unknown as FeedbackForm;
  }
  const res = await fetch(`${apiBase()}/feedback/form`);
  if (!res.ok) throw new FeedbackError("The form could not be loaded. Please refresh the page.", res.status);
  return (await res.json()) as FeedbackForm;
}

function randomHex(bytes: number): string {
  const a = new Uint8Array(bytes);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function submitFeedback(body: FeedbackSubmission): Promise<FeedbackSubmitResponse> {
  if (isMockMode()) {
    // Mock mode stores nothing anywhere.
    await delay(400);
    return { ok: true, response_id: randomHex(16) };
  }
  let res: Response;
  try {
    res = await fetch(`${apiBase()}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Taal-Visitor": getVisitorId() },
      body: JSON.stringify(body),
    });
  } catch {
    throw new FeedbackError("No connection. Your answers are still here; please try again.", 0);
  }
  if (res.ok) return (await res.json()) as FeedbackSubmitResponse;
  const message =
    res.status === 429
      ? "Too many submissions from this device. Please wait a while and try again."
      : res.status === 422
        ? "Some answers could not be accepted. Please check the form and try again."
        : "Your response could not be saved. Your answers are still here; please try again in a minute.";
  throw new FeedbackError(message, res.status);
}

export async function getFeedbackSummary(token: string): Promise<FeedbackSummary> {
  if (isMockMode()) {
    await delay(150);
    return mockFeedbackSummary as unknown as FeedbackSummary;
  }
  const res = await fetch(`${apiBase()}/feedback/summary`, { headers: { Authorization: `Bearer ${token}` } });
  if (res.status === 401) throw new FeedbackError("That token was not accepted.", 401);
  if (res.status === 503) throw new FeedbackError("Results are not enabled on this server.", 503);
  if (!res.ok) throw new FeedbackError(`Could not load results (${res.status}).`, res.status);
  return (await res.json()) as FeedbackSummary;
}
