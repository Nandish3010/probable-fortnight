import { test, expect } from "@playwright/test";
import { approveReducer, clockTime, formatElapsed, initialApproveState, workingCopy, type ApproveState } from "../../lib/approveMachine";
import { ApiError } from "../../lib/apiError";
import { chatUrlFor } from "../../lib/chatBridge";
import { chartSummary, niceCeil, separate, yTicks } from "../../lib/chartScale";
import { countUpValue, easeOutQuart } from "../../lib/countUp";
import { dayMonth } from "../../lib/format";
import { personaCaption } from "../../lib/playText";
import type { ApproveResponse, Play } from "../../lib/types";

// The pure parts of the Approve choreography: the state machine, the count-up maths, the chart
// scale, the persona caption. The browser behaviour is in approve-choreography.spec.ts.

const response = {
  play_id: "p",
  status: "approved",
  assignment: { treated_n: 291, holdout_n: 32, seed: "s" },
  forecast: { run_id: "r", model: "m", latency_ms: 1, series: [], writeoff_before_inr: 1, writeoff_after_inr: 0, play_window: { start: "", end: "" } },
  source: "live",
} as unknown as ApproveResponse;

const run = (actions: Parameters<typeof approveReducer>[1][], from: ApproveState = initialApproveState()) =>
  actions.reduce(approveReducer, from);

test.describe("approveReducer", () => {
  test("idle -> submitting -> animating -> settled, with the T0 timeline in between", () => {
    let s = initialApproveState();
    expect(s.phase).toBe("idle");
    s = run([{ type: "submit" }], s);
    expect(s).toMatchObject({ phase: "submitting", stepsTicked: 0, bodyShown: false });
    s = run([{ type: "respond", result: response, elapsedMs: 11800, reduced: false }], s);
    expect(s).toMatchObject({ phase: "animating", elapsedMs: 11800, animate: true, stepsTicked: 0, collapsed: false, bodyShown: false });
    s = run([{ type: "tick" }, { type: "tick" }, { type: "tick" }, { type: "tick" }], s);
    expect(s.stepsTicked).toBe(3); // never past three
    s = run([{ type: "collapse" }, { type: "reveal" }, { type: "chip" }], s);
    expect(s).toMatchObject({ collapsed: true, bodyShown: true, chipShown: true, phase: "animating" });
    s = run([{ type: "settle" }], s);
    expect(s.phase).toBe("settled");
  });

  test("reduced motion goes straight to settled with everything shown and no animation", () => {
    const s = run([{ type: "submit" }, { type: "respond", result: response, elapsedMs: 5, reduced: true }]);
    expect(s).toMatchObject({ phase: "settled", animate: false, stepsTicked: 3, collapsed: true, bodyShown: true, chipShown: true });
  });

  test("a 409 is already approved, with no animation and no result of its own", () => {
    const s = run([{ type: "submit" }, { type: "fail", error: new ApiError({ kind: "conflict", endpoint: "/approve", status: 409 }) }]);
    expect(s).toMatchObject({ phase: "alreadyApproved", result: null, animate: false, bodyShown: true });
  });

  test("a play the API already reports as approved starts in alreadyApproved, with its timestamp", () => {
    const s = initialApproveState({ alreadyApproved: true, approvedAt: "2026-09-12T03:42:00Z" });
    expect(s).toMatchObject({ phase: "alreadyApproved", approvedAt: "2026-09-12T03:42:00Z", animate: false });
    expect(approveReducer(s, { type: "submit" })).toBe(s); // terminal
  });

  test("any other failure is an error, and Retry (submit) leaves it", () => {
    const err = new ApiError({ kind: "http", endpoint: "/approve", status: 500 });
    let s = run([{ type: "submit" }, { type: "fail", error: err }]);
    expect(s).toMatchObject({ phase: "error", error: err });
    s = run([{ type: "submit" }], s);
    expect(s).toMatchObject({ phase: "submitting", error: null });
  });

  test("settled is terminal; actions out of order are ignored", () => {
    const settled = run([{ type: "submit" }, { type: "respond", result: response, elapsedMs: 1, reduced: true }]);
    expect(approveReducer(settled, { type: "submit" })).toBe(settled);
    expect(approveReducer(settled, { type: "fail", error: new ApiError({ kind: "http", endpoint: "/approve" }) })).toBe(settled);
    const idle = initialApproveState();
    expect(approveReducer(idle, { type: "tick" })).toBe(idle);
    expect(approveReducer(idle, { type: "respond", result: response, elapsedMs: 1, reduced: false })).toBe(idle);
    expect(approveReducer(idle, { type: "settle" })).toBe(idle);
  });

  test("the timer copy: the honest estimate, then the give-up line after 20 s", () => {
    expect(workingCopy(7)).toBe("Working: 7 s. This usually takes 10 to 13 s.");
    expect(workingCopy(19)).toBe("Working: 19 s. This usually takes 10 to 13 s.");
    expect(workingCopy(22)).toBe("Still working: 22 s. Taal gives up at 60 s and keeps your plan unchanged.");
    expect(formatElapsed(11800)).toBe("11.8 s");
  });

  test("clockTime is HH:MM in IST, and null for nothing or nonsense", () => {
    expect(clockTime("2026-09-12T03:42:00Z")).toBe("09:12");
    expect(clockTime(null)).toBeNull();
    expect(clockTime("not a date")).toBeNull();
  });
});

test.describe("count-up maths", () => {
  test("starts at 0, ends exactly on the target, and never overshoots", () => {
    expect(countUpValue(7497.87, 0, 900)).toBe(0);
    expect(countUpValue(7497.87, 900, 900)).toBe(7497.87);
    expect(countUpValue(7497.87, 5000, 900)).toBe(7497.87);
    for (let t = 0; t <= 900; t += 30) {
      const v = countUpValue(7497.87, t, 900);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(7497.87);
    }
  });

  test("is ease-out: more than half the way at the half-way time, and monotonic", () => {
    expect(countUpValue(1000, 450, 900)).toBeGreaterThan(900);
    let prev = -1;
    for (let t = 0; t <= 900; t += 10) {
      const v = countUpValue(1000, t, 900);
      expect(v).toBeGreaterThanOrEqual(prev);
      prev = v;
    }
    expect(easeOutQuart(-1)).toBe(0);
    expect(easeOutQuart(2)).toBe(1);
  });

  test("a negative target counts down to it", () => {
    expect(countUpValue(-500, 900, 900)).toBe(-500);
    expect(countUpValue(-500, 450, 900)).toBeLessThan(-400);
  });
});

test.describe("chart scale", () => {
  test("niceCeil rounds up to 1, 2, 3, 4, 6, 8 or 10 times a power of ten", () => {
    expect(niceCeil(0)).toBe(1);
    expect(niceCeil(23.2)).toBe(30);
    expect(niceCeil(24.9)).toBe(30);
    expect(niceCeil(30)).toBe(30);
    expect(niceCeil(31)).toBe(40);
    expect(niceCeil(0.7)).toBe(0.8);
    expect(niceCeil(900)).toBe(1000);
  });

  test("three ticks: zero, half, top, and the top is at or above the data", () => {
    const { ticks, top } = yTicks(25.5);
    expect(ticks).toEqual([0, 15, 30]);
    expect(top).toBeGreaterThanOrEqual(25.5);
  });

  test("separate keeps two labels apart and leaves far-apart ones alone", () => {
    expect(separate(100, 200, 16)).toEqual([100, 200]);
    const [a, b] = separate(100, 104, 16);
    expect(b - a).toBe(16);
    const [c, d] = separate(104, 100, 16);
    expect(c - d).toBe(16);
  });

  test("dayMonth: '12 Sep', '9 Oct', no year, no ISO", () => {
    expect(dayMonth("2026-09-12")).toBe("12 Sep");
    expect(dayMonth("2026-10-09")).toBe("9 Oct");
    expect(dayMonth(undefined)).toBe("");
  });

  test("the summary names the span, the peak and the window; it says so when the play adds nothing", () => {
    const series = [
      { date: "2026-09-12", baseline_p50: 14, play_p50: 23 },
      { date: "2026-09-13", baseline_p50: 12, play_p50: 20 },
      { date: "2026-10-09", baseline_p50: 9, play_p50: 9 },
    ];
    const text = chartSummary(series, "2026-09-12", "2026-09-18");
    expect(text).toContain("Forecast chart");
    expect(text).toContain("12 Sep to 9 Oct");
    expect(text).toContain("23 units a day with it against 14 without");
    expect(text).toContain("The offer window runs 12 Sep to 18 Sep.");
    expect(chartSummary(series.map((p) => ({ ...p, play_p50: p.baseline_p50 })))).toContain("adds no units");
    expect(chartSummary(series.slice(0, 1))).toContain("not enough points");
  });
});

test.describe("personaCaption", () => {
  const tea = { target: { sku: "SKU-DARJEELING-TEA-100G", node_ids: ["DS-04"] }, mechanic: "transfer_plus_nudge" } as unknown as Play;

  test("a holdout never receives the offer", () => {
    expect(personaCaption({ role: "holdout", home_node_id: "DS-04" }, tea)).toBe(
      "Holdout: never receives this offer, even after the play is approved.",
    );
  });

  test("a persona at a target store is in the treated group, named from the play's own labels", () => {
    expect(personaCaption({ role: "sample", home_node_id: "DS-04" }, tea)).toBe(
      "In the treated group once you approve the Darjeeling Tea 100G play (transfer stock, then nudge customers).",
    );
  });

  test("anyone else, and any case with no play, gets the neutral line: the data does not say more", () => {
    expect(personaCaption({ role: "sample", home_node_id: "DS-07" }, tea)).toBe("Receives the offer once the play is approved.");
    expect(personaCaption({ role: "sample", home_node_id: "DS-04" }, null)).toBe("Receives the offer once the play is approved.");
    expect(personaCaption(null, tea)).toBe("Receives the offer once the play is approved.");
  });

  test("no hard-coded chips wording", () => {
    expect(personaCaption({ role: "sample", home_node_id: "DS-04" }, tea)).not.toMatch(/chips/i);
  });
});

test("chatUrlFor carries the action to a page with no chat panel", () => {
  expect(chatUrlFor("holdout")).toBe("/chat?as=holdout");
  expect(chatUrlFor("prefill")).toBe("/chat?as=prefill");
});
