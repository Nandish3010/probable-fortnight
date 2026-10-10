import { test, expect } from "@playwright/test";
import { count, formatDateTime, formatDuration, inr, liftInPoints } from "../../lib/format";

// Number and time formats the UI writes itself (design_spec.md 8.6). No browser: pure functions.

test.describe("lib/format: durations", () => {
  test("seconds, not fractions of a minute", () => {
    expect(formatDuration(0.09 * 60)).toBe("5.4 s");
    expect(formatDuration(5)).toBe("5 s");
    expect(formatDuration(11.8)).toBe("12 s");
    expect(formatDuration(65)).toBe("1 min 5 s");
    expect(formatDuration(120)).toBe("2 min");
    expect(formatDuration(0.4)).toBe("0.4 s");
  });
  test("a missing or invalid value is a dash, never NaN", () => {
    expect(formatDuration(undefined)).toBe("–");
    expect(formatDuration(Number.NaN)).toBe("–");
    expect(formatDuration(-3)).toBe("–");
  });
});

test.describe("lib/format: grouping and dates", () => {
  test("rupees and counts use Indian digit grouping", () => {
    expect(inr(1795463.92)).toBe("₹17,95,464");
    expect(inr(35020)).toBe("₹35,020");
    expect(count(1234567)).toBe("12,34,567");
    expect(count(null)).toBe("0");
  });
  test("formatDateTime is a fixed month name and a 24-hour clock", () => {
    const out = formatDateTime("2026-09-12T03:30:00Z");
    expect(out).toMatch(/^12 Sep, \d{2}:\d{2}$/);
    expect(out).not.toMatch(/am|pm|Sept/i);
    expect(formatDateTime(undefined)).toBe("–");
  });
});

test.describe("lib/format: lift in points", () => {
  test("uses the API's *_pp fields when present", () => {
    expect(liftInPoints({ lift: 0.003096, ci_low: -0.113902, ci_high: 0.017326, lift_pp: 0.31, ci_low_pp: -11.39, ci_high_pp: 1.733 })).toBe(
      "response-rate difference, +0.3 percentage points (95% CI -11.4 to +1.7 points)",
    );
  });
  test("an older API without *_pp fields is formatted from its fractions", () => {
    expect(liftInPoints({ lift: 0.023, ci_low: -0.093, ci_high: 0.061 })).toBe(
      "response-rate difference, +2.3 percentage points (95% CI -9.3 to +6.1 points)",
    );
  });
  test("no lift, no sentence", () => {
    expect(liftInPoints({})).toBeNull();
  });
});
