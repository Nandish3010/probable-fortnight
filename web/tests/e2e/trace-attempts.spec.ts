import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { buildAttempts, rejectionsFromErrors } from "../../components/traceAttempts";
import type { TraceEvent } from "../../lib/types";

// The data shape behind the trace panel's "guardrail attempts" list. No browser: this is the pure
// pairing of propose_play calls with their responses.

function ev(seq: number, extra: Partial<TraceEvent>): TraceEvent {
  return { seq, run_id: "r", invocation_id: "e-1", author: "planner", timestamp: "0", ts_offset_ms: seq * 100, ...extra };
}
const call = (seq: number, rationale: string, more: Partial<TraceEvent> = {}) =>
  ev(seq, { function_call: { name: "propose_play", args: { play: { rationale } } }, ...more });
const resp = (seq: number, valid: boolean, errors: string[], more: Partial<TraceEvent> = {}) =>
  ev(seq, { function_response: { name: "propose_play", response: { valid, errors } }, ...more });

test.describe("buildAttempts", () => {
  test("pairs each call with its response: rejected attempts carry guardrail, reason and the rejected rationale", () => {
    const attempts = buildAttempts([
      ev(0, { author: "cost_governor", text: "rupees at stake 9200" }),
      call(1, "first wording"),
      resp(2, false, ["guardrail cite_or_drop: uncited numbers in rationale: 52"]),
      call(3, "second wording"),
      resp(4, true, []),
    ]);
    expect(attempts).toEqual([
      { n: 1, pending: false, accepted: false, rejections: [{ guardrail: "cite_or_drop", reason: "uncited numbers in rationale: 52" }], rationale: "first wording", rationaleCut: false, offsetMs: 200 },
      { n: 2, pending: false, accepted: true, rejections: [], rationale: "second wording", rationaleCut: false, offsetMs: 400 },
    ]);
  });

  test("prefers the recorded fields (attempt, full rationale, rejections) over what it can derive", () => {
    const cutCopy = "x".repeat(400) + "...";
    const [a] = buildAttempts([
      call(1, cutCopy, { attempt: 3, rationale: "the full wording, past the 400-character cut" }),
      resp(2, false, ["guardrail margin_floor: raw string"], { attempt: 3, rejections: [{ guardrail: "margin_floor", reason: "recorded reason" }] }),
    ]);
    expect(a.n).toBe(3);
    expect(a.rationale).toBe("the full wording, past the 400-character cut");
    expect(a.rationaleCut).toBe(false);
    expect(a.rejections).toEqual([{ guardrail: "margin_floor", reason: "recorded reason" }]);
  });

  test("an older trace: the rationale is the 400-character copy and is flagged as cut", () => {
    const [a] = buildAttempts([call(1, "y".repeat(400) + "..."), resp(2, false, ["$: 'play_id' is a required property"])]);
    expect(a.rationaleCut).toBe(true);
    expect(a.rejections).toEqual([{ guardrail: "schema", reason: "$: 'play_id' is a required property" }]);
  });

  test("a call with no response yet (a live run mid-check) is pending, not rejected", () => {
    const attempts = buildAttempts([call(1, "w"), resp(2, false, ["guardrail frequency_cap: x"]), call(3, "w2")]);
    expect(attempts.map((a) => [a.n, a.pending, a.accepted])).toEqual([[1, false, false], [2, true, false]]);
  });

  test("a trace with no propose_play (governor skip, rules fallback) has no attempts", () => {
    expect(buildAttempts([ev(0, { text: "skipped" })])).toEqual([]);
  });

  test("rejectionsFromErrors names the rule when the string does, else 'schema'", () => {
    expect(rejectionsFromErrors(["guardrail holdout_required: fraction 0.02 < 0.05", "other"])).toEqual([
      { guardrail: "holdout_required", reason: "fraction 0.02 < 0.05" },
      { guardrail: "schema", reason: "other" },
    ]);
    expect(rejectionsFromErrors(undefined)).toEqual([]);
  });

  test("the committed flagship recording: three cite_or_drop rejections, then the passing attempt", () => {
    const file = path.resolve(__dirname, "../../../eval/raw/planner_real_traces_2026-09-28/run_04/trace.jsonl");
    const events = fs.readFileSync(file, "utf-8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as TraceEvent);
    const attempts = buildAttempts(events);
    expect(attempts.map((a) => [a.n, a.accepted])).toEqual([[1, false], [2, false], [3, false], [4, true]]);
    for (const a of attempts.slice(0, 3)) {
      expect(a.rejections).toEqual([{ guardrail: "cite_or_drop", reason: "uncited numbers in rationale: 52" }]);
      expect(a.rationaleCut).toBe(false);
    }
    expect(attempts[0].rationale!.length).toBeGreaterThan(400);
  });
});
