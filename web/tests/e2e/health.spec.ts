import { test, expect } from "@playwright/test";
import { formatLatency, modelChipText, modelInfoFromHealth, parseVertexModel, traceDurationMs } from "../../lib/health";
import { mockFixture } from "./helpers";

// What the model chip reads from /health. No browser: pure functions.

const LIVE =
  "credentials + project resolved (project=amru-509214, model=gemini-3.5-flash, fallback=gemini-3.5-flash-lite); generateContent not called by this check";
const STUB = "stub backend; no live Vertex call (model id if live: gemini-3.5-flash)";
const health = (detail: string | undefined, model_fallback?: string) =>
  ({ checks: { vertex: { ok: true, checked_at: "x", detail } }, model_fallback }) as never;

test.describe("lib/health: the model named by /health", () => {
  test("a live detail string names the model; the fallback comes from model_fallback, not the detail", () => {
    expect(parseVertexModel(LIVE)).toEqual({ model: "gemini-3.5-flash", live: true });
    expect(modelInfoFromHealth(health(LIVE, "gemini-3.5-flash-lite"))).toEqual({ model: "gemini-3.5-flash", fallback: "gemini-3.5-flash-lite", live: true });
  });
  test("without a fallback there is none to show", () => {
    expect(modelInfoFromHealth(health(LIVE))?.fallback).toBeNull();
    expect(modelInfoFromHealth(health(LIVE, "gemini-3.5-flash"))?.fallback).toBeNull();
  });
  test("the stub backend names the model it would use live and says so", () => {
    expect(modelInfoFromHealth(health(STUB, "gemini-3.5-flash-lite"))).toEqual({ model: "gemini-3.5-flash", fallback: "gemini-3.5-flash-lite", live: false });
    expect(modelChipText(modelInfoFromHealth(health(STUB))!).title).toContain("stub backend");
  });
  test("a missing detail, a detail without a model, or no vertex check is no model at all", () => {
    expect(modelInfoFromHealth(health(undefined))).toBeNull();
    expect(modelInfoFromHealth(health("credentials missing"))).toBeNull();
    expect(modelInfoFromHealth({ checks: {} } as never)).toBeNull();
    expect(modelInfoFromHealth(null)).toBeNull();
    expect(parseVertexModel("model=")).toBeNull();
  });
  test("the shipped mock health names gemini-3.5-flash", () => {
    expect(modelInfoFromHealth(mockFixture("health"))?.model).toBe("gemini-3.5-flash");
  });
});

test.describe("lib/health: run time and chip text", () => {
  test("latency is one decimal in seconds, and absent when unknown", () => {
    expect(formatLatency(1234)).toBe("1.2 s");
    expect(formatLatency(20_000)).toBe("20.0 s");
    expect(formatLatency(null)).toBeNull();
    expect(formatLatency(undefined)).toBeNull();
    expect(formatLatency(0)).toBeNull();
    expect(formatLatency(Number.NaN)).toBeNull();
  });
  test("a trace's duration is its last event offset", () => {
    expect(traceDurationMs([{ ts_offset_ms: 0 }, { ts_offset_ms: 4200 }, { ts_offset_ms: 1900 }])).toBe(4200);
    expect(traceDurationMs([])).toBeNull();
  });
  test("chip text is 'model · time', or just the model, and the fallback sits in the tooltip", () => {
    const info = { model: "gemini-3.5-flash", fallback: "gemini-3.5-flash-lite", live: true };
    const withTime = modelChipText(info, 1234);
    expect(withTime.text).toBe("gemini-3.5-flash · 1.2 s");
    expect(withTime.title).toContain("gemini-3.5-flash-lite");
    expect(withTime.text).not.toContain("lite");
    expect(modelChipText(info).text).toBe("gemini-3.5-flash");
    expect(modelChipText(info, 0).text).toBe("gemini-3.5-flash");
  });
});
