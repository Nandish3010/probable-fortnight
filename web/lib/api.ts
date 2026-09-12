// Taal API client. Talks to the real backend (docs/openapi.yaml) unless
// NEXT_PUBLIC_TAAL_MOCK=1, in which case every route is served from the
// static fixtures under web/mocks/*.json (bundled at build time).
import type {
  ApproveRequest,
  ApproveResponse,
  CaptureRequest,
  ChatEnvelope,
  ChatRequest,
  EventsResponse,
  ExecutionRequest,
  ExecutionResponse,
  Gap,
  HealthResponse,
  Outcome,
  Play,
  PolicyDoc,
  RerunRequest,
  RerunResponse,
  ResetResponse,
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
import mockChat from "../mocks/chat.json";

export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_TAAL_MOCK === "1";
}

function apiBase(): string {
  return process.env.NEXT_PUBLIC_TAAL_API_URL ?? "http://localhost:8080";
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

export async function getGaps(params?: { node_id?: string }): Promise<Gap[]> {
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
  const qs = params?.node_id ? `?node_id=${encodeURIComponent(params.node_id)}` : "";
  return request<Gap[]>(`/gaps${qs}`);
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

export async function getOutcomes(): Promise<Outcome[]> {
  if (isMockMode()) {
    await delay(150);
    return mockOutcomes as unknown as Outcome[];
  }
  return request<Outcome[]>("/outcomes");
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

function pickMockScenario(text: string): ChatEnvelope[] {
  const t = text.toLowerCase();
  const chat = mockChat as unknown as Record<string, ChatEnvelope[]>;
  if (t.includes("stop")) return chat.stop;
  if (t.startsWith("add:") || t.startsWith("add ") || t.startsWith("order")) return chat.order;
  if (t.includes("cola") || t.includes("zero")) return chat.cola_zero;
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
    const envelopes = pickMockScenario(req.text);
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
