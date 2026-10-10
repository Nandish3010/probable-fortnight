import { test, expect } from "@playwright/test";
import { count, formatDateTime, formatDuration, inr } from "../../lib/format";

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
