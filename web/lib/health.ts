// What /health says about the model, read for the model chip (components/ModelChip.tsx). Pure and
// unit-tested in node (tests/e2e/health.spec.ts). Nothing here invents a model id: when the health
// response names none, the result is null and the chip renders nothing.
import { dayMonth } from "./format";
import type { HealthResponse, PlanLiveEval } from "./types";

export interface ModelInfo {
  /** The model id named by the vertex check, e.g. "gemini-3.5-flash". */
  model: string;
  /** The id used when the primary is unavailable (`model_fallback`), shown only in the tooltip. */
  fallback: string | null;
  /** False when the backend is the scripted stub: the id is the one that would serve live. */
  live: boolean;
}

const ID = "([A-Za-z0-9][A-Za-z0-9._-]*)";

/** Reads the model id out of the vertex check's detail string. Two shapes exist:
 * live: "credentials + project resolved (project=p, model=gemini-3.5-flash, fallback=gemini-3.5-flash-lite); ..."
 * stub: "stub backend; no live Vertex call (model id if live: gemini-3.5-flash)". */
export function parseVertexModel(detail: string | null | undefined): { model: string; live: boolean } | null {
  if (!detail) return null;
  const live = detail.match(new RegExp(`\\bmodel=${ID}`));
  if (live) return { model: live[1], live: true };
  const stub = detail.match(new RegExp(`model id if live:\\s*${ID}`));
  if (stub) return { model: stub[1], live: false };
  return null;
}

export function modelInfoFromHealth(health: Pick<HealthResponse, "checks" | "model_fallback" | "model" | "backend"> | null | undefined): ModelInfo | null {
  // A top-level `model` (when /health carries one) wins; the vertex detail string is the fallback
  // and also says whether the backend is live or the stub.
  const fromDetail = parseVertexModel(health?.checks?.vertex?.detail);
  const top = typeof health?.model === "string" && new RegExp(`^${ID}$`).test(health.model.trim()) ? health.model.trim() : null;
  const parsed = top ? { model: top, live: fromDetail ? fromDetail.live : health?.backend === "vertex" } : fromDetail;
  if (!parsed) return null;
  const fallback = health?.model_fallback?.trim() || null;
  return { ...parsed, fallback: fallback && fallback !== parsed.model ? fallback : null };
}

/** Which model the chip names. The run's own model (its run_summary.model) wins: a recording keeps naming
 * the model that wrote it after the configuration changes. A run that names a model which is not a Gemini
 * id (the scripted planner's "stub-planner") gets no chip. /health (the model configured today) is used
 * only for a run that names none, e.g. the in-flight chip of a Plan live run that has no summary yet. */
export function chipModel(runModel: string | null | undefined, health: ModelInfo | null): ModelInfo | null {
  const own = typeof runModel === "string" ? runModel.trim() : "";
  if (own) return /^gemini-[A-Za-z0-9._-]+$/.test(own) ? { model: own, fallback: null, live: true } : null;
  return health;
}

/** "1.2 s" from milliseconds; null when the duration is unknown or not a positive number. */
export function formatLatency(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms <= 0) return null;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** A trace's duration: the largest event offset, or null when there are no events. */
export function traceDurationMs(events: readonly { ts_offset_ms: number }[]): number | null {
  let max = 0;
  for (const e of events) if (Number.isFinite(e.ts_offset_ms) && e.ts_offset_ms > max) max = e.ts_offset_ms;
  return max > 0 ? max : null;
}

/** The chip's text and tooltip. */
export function modelChipText(info: ModelInfo, latencyMs?: number | null): { text: string; title: string } {
  const lat = formatLatency(latencyMs);
  const title = [
    info.live ? `Model: ${info.model}` : `Model if live: ${info.model} (stub backend, no live call)`,
    info.fallback ? `Fallback: ${info.fallback}` : null,
    lat ? `Run time: ${lat}` : null,
  ]
    .filter(Boolean)
    .join(". ");
  return { text: lat ? `${info.model} · ${lat}` : info.model, title };
}

/** "Committed eval: 22/24 passed (11 Oct), p50 26.5 s" from /health `plan_live_eval`; null when the field is
 * absent or malformed (older deploys do not carry it), so the chip simply does not render. */
export function planLiveEvalText(ev: Partial<PlanLiveEval> | null | undefined): string | null {
  if (!ev) return null;
  const { passed, total, p50_s, date } = ev;
  if (typeof passed !== "number" || typeof total !== "number" || !Number.isFinite(passed) || !Number.isFinite(total) || total <= 0 || passed < 0 || passed > total) return null;
  const when = date ? dayMonth(date) : "";
  const p50 = typeof p50_s === "number" && Number.isFinite(p50_s) && p50_s > 0 ? `, p50 ${p50_s.toFixed(1)} s` : "";
  return `Committed eval: ${passed}/${total} passed${when ? ` (${when})` : ""}${p50}`;
}

/** Which provenances may carry the model chip: only runs a model actually authored. A scripted
 * fixture shows its own badge alone and a rules fallback shows nothing. */
export function showsModelChip(source: string | null | undefined): boolean {
  return source === "recorded_gemini" || source === "live_gemini";
}
