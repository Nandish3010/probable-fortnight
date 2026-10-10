// Taal API client. Talks to the real backend (docs/openapi.yaml) unless
// NEXT_PUBLIC_TAAL_MOCK=1, in which case every route is served from the static
// fixtures under web/mocks/*.json (loaded on demand by lib/mockData.ts, only in mock mode).
//
// Every real request goes through apiFetch()/apiFetchRaw(): one AbortController per request, a
// per-endpoint timeout, and a typed ApiError (lib/apiError.ts) so no caller can be left on a
// spinner that never ends. components/ErrorCard.tsx renders those errors.
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
import { ApiError, errorFromResponse, toApiError } from "./apiError";
import { mockApproveFor, mockJson } from "./mockData";
import { mockDelayMs, mockGate } from "./mockFaults";
import { clearMockMeasure, mockMeasure, mockMeasuredRows, rememberMockOrder } from "./mockMeasure";
import { getVisitorId } from "./visitor";

export { ApiError, toApiError } from "./apiError";
export type { ApiErrorKind } from "./apiError";

// Test hook, honoured only in a build made with NEXT_PUBLIC_TAAL_MOCK=1 (a production build folds
// the check to false and drops this): localStorage "taal_force_live" = "1" makes the app use the
// real request path (apiFetch) against the URL in "taal_api_url" instead of the fixtures, so a
// browser test can aim the real wrapper at an unreachable or fake origin (blocked-origin.spec.ts).
function liveOverride(key: string): string | null {
  if (process.env.NEXT_PUBLIC_TAAL_MOCK !== "1") return null;
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function isMockMode(): boolean {
  if (process.env.NEXT_PUBLIC_TAAL_MOCK !== "1") return false;
  return liveOverride("taal_force_live") !== "1";
}

function apiBase(): string {
  // Strip a trailing slash so `${apiBase()}${path}` (path always starts with "/") never
  // produces a double slash, which 404s against FastAPI's exact route paths.
  const base = liveOverride("taal_api_url") ?? process.env.NEXT_PUBLIC_TAAL_API_URL ?? "http://localhost:8080";
  return base.replace(/\/+$/, "");
}

async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------- the one request wrapper ----------

export const DEFAULT_TIMEOUT_MS = 10_000;

// First match wins. /rerun and /plan answer 202 quickly today, but a planner call is allowed to
// take most of two minutes, so they get the longest budget; a chat turn or a photo read is
// allowed 20 s; everything else (a read) is expected back in 10.
const TIMEOUTS: ReadonlyArray<readonly [RegExp, number]> = [
  [/^\/approve(\/|$)/, 60_000],
  [/^\/(plan|rerun)(\/|$)/, 100_000],
  [/^\/chat(\/|$)/, 20_000],
  [/^\/capture(\/|$)/, 20_000],
  [/^\/measure(\/|$)/, 30_000],
];

export function timeoutFor(path: string): number {
  const pathname = path.split("?")[0];
  return TIMEOUTS.find(([re]) => re.test(pathname))?.[1] ?? DEFAULT_TIMEOUT_MS;
}

export interface RequestOptions {
  /** Overrides the per-endpoint timeout. */
  timeoutMs?: number;
  /** A caller's own abort (e.g. unmount). It is rethrown as an AbortError, not mapped to an ApiError. */
  signal?: AbortSignal;
}

async function runRequest<T>(
  path: string,
  init: RequestInit | undefined,
  opts: RequestOptions | undefined,
  // Runs while the timer is still armed: for JSON the body read is timed too, for a stream it is
  // the identity so a long stream is not cut by the header timeout.
  consume: (res: Response) => Promise<T>,
): Promise<T> {
  const endpoint = path.split("?")[0];
  const headers = new Headers(init?.headers);
  headers.set("X-Taal-Visitor", getVisitorId());
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, opts?.timeoutMs ?? timeoutFor(path));
  const outer = opts?.signal;
  const onOuterAbort = () => controller.abort();
  if (outer) {
    if (outer.aborted) controller.abort();
    else outer.addEventListener("abort", onOuterAbort, { once: true });
  }

  try {
    let res: Response;
    try {
      res = await fetch(`${apiBase()}${path}`, { ...init, headers, credentials: "include", signal: controller.signal });
    } catch (e) {
      if (timedOut) throw new ApiError({ kind: "timeout", endpoint });
      if (outer?.aborted) throw e;
      // A TypeError: CORS block, refused connection, DNS failure, offline.
      throw new ApiError({ kind: "network", endpoint, message: e instanceof Error ? e.message : undefined });
    }
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw errorFromResponse(endpoint, res.status, body, res.headers.get("Retry-After"));
    }
    try {
      return await consume(res);
    } catch (e) {
      if (e instanceof ApiError) throw e;
      if (timedOut) throw new ApiError({ kind: "timeout", endpoint });
      if (outer?.aborted) throw e;
      throw toApiError(e, endpoint);
    }
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener("abort", onOuterAbort);
  }
}

/** Fetch + status check + JSON, with a timeout and a typed ApiError. */
export function apiFetch<T>(path: string, init?: RequestInit, opts?: RequestOptions): Promise<T> {
  return runRequest<T>(path, init, opts, async (res) => (await res.json()) as T);
}

/** Same checks, but hands back the Response once its headers arrive (for streams). The timeout
 * covers the wait for headers only. */
export function apiFetchRaw(path: string, init?: RequestInit, opts?: RequestOptions): Promise<Response> {
  return runRequest<Response>(path, init, opts, async (res) => res);
}

// ---------- health ----------

export async function getHealth(): Promise<HealthResponse> {
  if (isMockMode()) {
    await mockGate("/health");
    await delay(120);
    return (await mockJson("health")) as HealthResponse;
  }
  return apiFetch<HealthResponse>("/health");
}

// ---------- gaps ----------

export async function getGaps(params?: { node_id?: string; limit?: number }): Promise<Gap[]> {
  if (isMockMode()) {
    await mockGate("/gaps");
    await delay(150);
    const all = (await mockJson("gaps")) as Gap[];
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
  return apiFetch<Gap[]>(`/gaps?${q.toString()}`);
}

// ---------- plays ----------

// Mock mode keeps what the visitor approved, like the real sandbox does, so /plays reports it as
// approved afterwards. Cleared by Reset. (A test simulates a restarted server by removing this key.)
const MOCK_APPROVED_KEY = "taal_mock_approved";

function mockApprovedIds(): string[] {
  try {
    const raw = typeof window === "undefined" ? null : window.localStorage.getItem(MOCK_APPROVED_KEY);
    const v = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function rememberMockApproval(playId: string) {
  try {
    const ids = mockApprovedIds();
    if (!ids.includes(playId)) window.localStorage.setItem(MOCK_APPROVED_KEY, JSON.stringify([...ids, playId]));
  } catch {
    // Storage blocked: the play then simply stays "proposed" in mock mode.
  }
}

export async function getPlays(params?: { gap_id?: string }): Promise<Play[]> {
  if (isMockMode()) {
    await mockGate("/plays");
    await delay(150);
    const approvedIds = mockApprovedIds();
    const all = ((await mockJson("plays")) as unknown as Play[]).map((p) =>
      approvedIds.includes(p.play_id) ? { ...p, status: "approved" as const, approved_at: p.approved_at ?? new Date().toISOString() } : p,
    );
    if (params?.gap_id) return all.filter((p) => p.gap_id === params.gap_id);
    return all;
  }
  const qs = params?.gap_id ? `?gap_id=${encodeURIComponent(params.gap_id)}` : "";
  return apiFetch<Play[]>(`/plays${qs}`);
}

// ---------- approve ----------

export async function approve(req: ApproveRequest): Promise<ApproveResponse> {
  if (isMockMode()) {
    await mockGate("/approve");
    await delay(mockDelayMs("/approve", 1100));
    const res = await mockApproveFor(req.play_id);
    rememberMockApproval(req.play_id);
    return res;
  }
  return apiFetch<ApproveResponse>("/approve", { method: "POST", body: JSON.stringify(req) });
}

// ---------- rerun (policy change -> re-plan) ----------
//
// POST /rerun is asynchronous (202 Accepted; the planner runs on a worker thread after the
// response lands -- a live Gemini call takes 20-45s). Follow the returned stream_url with
// streamRerun() for a live-updating trace, or poll status_url with getRerunStatus(); either
// resolves to the same RerunResult shape.

export async function rerun(req: RerunRequest): Promise<RerunAccepted> {
  if (isMockMode()) {
    await mockGate("/rerun");
    await delay(300);
    const base = (await mockJson("rerun")) as unknown as RerunResult;
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
    return await apiFetch<RerunAccepted>("/rerun", { method: "POST", body: JSON.stringify(req) });
  } catch (e) {
    if (e instanceof ApiError && e.kind === "conflict") {
      throw new ApiError({
        kind: "conflict",
        endpoint: e.endpoint,
        status: e.status,
        message: "A re-plan is already running for this visitor. Wait for it to finish, then try again.",
      });
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
    await mockGate(`/events/${runId}/stream`);
    const frames = (await mockJson("rerun_events")) as unknown as { event: string; data: unknown }[];
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
    return result ?? ((await mockJson("rerun")) as unknown as RerunResult);
  }

  // The header timeout (10 s) applies to the response starting; the stream itself runs as long
  // as the run does.
  const res = await apiFetchRaw(`/events/${encodeURIComponent(runId)}/stream`, undefined, { signal });

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
    await mockGate(`/rerun/${runId}`);
    await delay(150);
    const result = (await mockJson("rerun")) as unknown as RerunResult;
    const now = new Date().toISOString();
    return { run_id: runId, status: "done", started_at: now, finished_at: now, result };
  }
  return apiFetch<RerunStatus>(`/rerun/${encodeURIComponent(runId)}`);
}

// ---------- policy ----------

export async function getPolicy(): Promise<PolicyDoc> {
  if (isMockMode()) {
    await mockGate("/policy");
    await delay(100);
    return (await mockJson("policy")) as unknown as PolicyDoc;
  }
  return apiFetch<PolicyDoc>("/policy");
}

// ---------- events / trace ----------

export async function getEvents(runId: string): Promise<EventsResponse> {
  if (isMockMode()) {
    await mockGate(`/events/${runId}`);
    await delay(150);
    return (await mockJson("events")) as unknown as EventsResponse;
  }
  return apiFetch<EventsResponse>(`/events/${encodeURIComponent(runId)}`);
}

// ---------- capture (phone view) ----------

export async function capture(req: CaptureRequest): Promise<VisionIntakeResult> {
  if (isMockMode()) {
    await mockGate("/capture");
    await delay(1400);
    // Pallet 6 is the one sample with a row under the confidence threshold (the confirm step);
    // every other sample, and an upload, reads as the high-confidence Pallet 1.
    const base = (await mockJson(req.photo_ref?.endsWith("pallet_06.jpg") ? "capture_lowconf" : "capture")) as unknown as VisionIntakeResult;
    return { ...base, node_id: req.node_id, photo_ref: req.photo_ref ?? base.photo_ref };
  }
  return apiFetch<VisionIntakeResult>("/capture", { method: "POST", body: JSON.stringify(req) });
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
    await mockGate("/capture/confirm");
    await delay(200);
    return { ok: true, written: req.rows.length, batches: [], skipped: [], gaps_refreshed: 0 };
  }
  return apiFetch<CaptureConfirmResponse>("/capture/confirm", { method: "POST", body: JSON.stringify(req) });
}

// ---------- execution ----------

export async function execution(req: ExecutionRequest): Promise<ExecutionResponse> {
  if (isMockMode()) {
    await mockGate("/execution");
    await delay(300);
    return (await mockJson("execution")) as ExecutionResponse;
  }
  return apiFetch<ExecutionResponse>("/execution", { method: "POST", body: JSON.stringify(req) });
}

// ---------- outcomes ----------

export async function getDemoCustomers(playId = "play_chips_ds07_v1"): Promise<DemoCustomer[]> {
  if (isMockMode()) {
    await mockGate("/customers/demo");
    await delay(150);
    return (await mockJson("customers_demo")) as unknown as DemoCustomer[];
  }
  return apiFetch<DemoCustomer[]>(`/customers/demo?play_id=${encodeURIComponent(playId)}`);
}

export async function getOutcomes(): Promise<Outcome[]> {
  if (isMockMode()) {
    await mockGate("/outcomes");
    await delay(150);
    return [...((await mockJson("outcomes")) as unknown as Outcome[]), ...mockMeasuredRows()];
  }
  return apiFetch<Outcome[]>("/outcomes");
}

// Built once with the tenant and served from the base data dir, so it is the same for every
// visitor and "Reset demo data" does not change it.
export async function getPriorUpdate(): Promise<PriorUpdate> {
  if (isMockMode()) {
    await mockGate("/outcomes/prior-update");
    await delay(150);
    return (await mockJson("prior_update")) as unknown as PriorUpdate;
  }
  return apiFetch<PriorUpdate>("/outcomes/prior-update");
}

// Joins play_assignments to order_lines for every approved play and writes play_outcomes; the
// only thing that ever populates /outcomes. Nothing calls this automatically -- a fresh visitor
// sandbox has an approved play with zero outcomes until Measure runs at least once.
export async function postMeasure(): Promise<MeasureResponse> {
  if (isMockMode()) {
    await mockGate("/measure");
    await delay(600);
    const fixture = (await mockJson("outcomes")) as unknown as Outcome[];
    // Plays the visitor approved and ordered for are measured too (a SYNTHETIC row; lib/mockMeasure.ts).
    const rows = [...fixture, ...(await mockMeasure(mockApprovedIds(), fixture))];
    return {
      plays: rows.length,
      measured: rows.filter((r) => r.status === "measured").length,
      unmeasured: rows.filter((r) => r.status !== "measured").length,
      computed_at: new Date().toISOString(),
    };
  }
  return apiFetch<MeasureResponse>("/measure", { method: "POST" });
}

// ---------- reset ----------

export async function resetDemoData(): Promise<ResetResponse> {
  if (isMockMode()) {
    await mockGate("/reset");
    await delay(300);
    try {
      window.localStorage.removeItem(MOCK_APPROVED_KEY);
      clearMockMeasure();
    } catch {
      // nothing stored
    }
    return { ok: true, namespace: getVisitorId(), restored_from: "snapshot:mock" };
  }
  return apiFetch<ResetResponse>("/reset", { method: "POST" });
}

// ---------- chat ----------

async function pickMockScenario(req: ChatRequest): Promise<ChatEnvelope[]> {
  const t = req.text.toLowerCase();
  const chat = (await mockJson("chat")) as unknown as Record<string, ChatEnvelope[]>;
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
// A 503 {"error":"model_unavailable","retry_after_s":30} from the real endpoint (or the same
// fault injected in mock mode, lib/mockFaults.ts) arrives as an ApiError of kind model_unavailable.
export async function sendChat(
  req: ChatRequest,
  onEnvelope: (envelope: ChatEnvelope, latencyMs: number) => void,
  opts?: RequestOptions,
): Promise<void> {
  if (isMockMode()) {
    await mockGate("/chat");
    const envelopes = await pickMockScenario(req);
    rememberMockOrder(req.session_id, req.text);
    const extra = mockDelayMs("/chat", 0);
    for (const envelope of envelopes) {
      const latency = envelope.latency_ms ?? 900;
      await delay(Math.min(latency, 1600) + extra);
      if (opts?.signal?.aborted) return;
      onEnvelope({ ...envelope, session_id: req.session_id, ts: new Date().toISOString() }, latency);
    }
    return;
  }

  const started = Date.now();
  const res = await apiFetchRaw("/chat", { method: "POST", body: JSON.stringify(req) }, opts);

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
    return (await mockJson("feedback_form")) as unknown as FeedbackForm;
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
    return (await mockJson("feedback_summary")) as unknown as FeedbackSummary;
  }
  const res = await fetch(`${apiBase()}/feedback/summary`, { headers: { Authorization: `Bearer ${token}` } });
  if (res.status === 401) throw new FeedbackError("That token was not accepted.", 401);
  if (res.status === 503) throw new FeedbackError("Results are not enabled on this server.", 503);
  if (!res.ok) throw new FeedbackError(`Could not load results (${res.status}).`, res.status);
  return (await res.json()) as FeedbackSummary;
}
