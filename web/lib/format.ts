export function inr(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "₹0";
  const rounded = Math.round(value);
  return `₹${rounded.toLocaleString("en-IN")}`;
}

/** `inr()` with the sign in front of the symbol: `-₹8,423`, not `₹-8,423`. Positive stays `₹8,423`. */
export function inrSigned(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "₹0";
  const s = inr(Math.abs(value));
  return Math.round(value) < 0 ? `-${s}` : s;
}

/** A signed number of percentage points from a fraction (0.0229 -> "+2.3"). ASCII hyphen for the
 * minus so the string is easy to copy and to assert on. */
export function points(fraction: number, digits = 1): string {
  return pointsFromPp(fraction * 100, digits);
}

/** A signed number of percentage points from a value already in points (2.29 -> "+2.3"). */
export function pointsFromPp(pp: number, digits = 1): string {
  const fixed = pp.toFixed(digits);
  // "-0.0" reads as a sign flip on nothing; show it as a plain 0.0.
  if (Number(fixed) === 0) return (0).toFixed(digits);
  return pp > 0 ? `+${fixed}` : fixed;
}

export interface LiftFields {
  lift?: number | null;
  ci_low?: number | null;
  ci_high?: number | null;
  lift_pp?: number | null;
  ci_low_pp?: number | null;
  ci_high_pp?: number | null;
}

/** "response-rate difference, +2.3 percentage points (95% CI -9.3 to +6.1 points)". Uses the API's
 * *_pp fields when present, else the fractional fields formatted as points. Returns null when
 * there is no lift to describe. `lift` is treated-minus-holdout response rate, not a relative lift. */
export function liftInPoints(f: LiftFields, digits = 1): string | null {
  const lift = f.lift_pp ?? (f.lift != null ? f.lift * 100 : null);
  if (lift === null || lift === undefined) return null;
  const lo = f.ci_low_pp ?? (f.ci_low != null ? f.ci_low * 100 : null);
  const hi = f.ci_high_pp ?? (f.ci_high != null ? f.ci_high * 100 : null);
  const ci = lo !== null && lo !== undefined && hi !== null && hi !== undefined
    ? ` (95% CI ${pointsFromPp(lo, digits)} to ${pointsFromPp(hi, digits)} points)`
    : "";
  return `response-rate difference, ${pointsFromPp(lift, digits)} percentage points${ci}`;
}

export function pct(value: number | undefined | null, digits = 1): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "–";
  return `${(value * 100).toFixed(digits)}%`;
}

export function daysUntil(dateStr: string, now: Date = new Date()): number {
  const target = new Date(`${dateStr}T00:00:00Z`);
  const nowUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const ms = target.getTime() - nowUtc.getTime();
  return Math.ceil(ms / 86_400_000);
}

export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return "–";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(dateStr: string | undefined | null): string {
  if (!dateStr) return "–";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  // "12 Sep, 09:00": fixed month names and a 24-hour clock, in the reader's own time zone, so the
  // text does not depend on the runtime's ICU data ("Sept", "09:00 am").
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${hh}:${mm}`;
}

// ---------- relative dates (design_spec.md 8.3) ----------
// Deadlines read as "in 6 days" / "6 days ago", with the absolute date one hover (title) away.
// All of it is relative to the demo clock the server reports (lib/useServerNow.ts), never the
// browser's own clock. Dates are compared as UTC calendar days, like daysUntil above, and the
// month and weekday names are fixed tables so the output does not depend on the runtime's ICU data.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** A date shown beyond this many days from the demo clock is written as a plain date. */
export const RELATIVE_DATE_LIMIT_DAYS = 60;
/** Within this many days, the short date carries its weekday ("Fri 18 Sep"). */
export const WEEKDAY_LIMIT_DAYS = 14;

export interface RelativeDate {
  /** Whole days from the demo date to the target (negative: in the past). */
  days: number;
  /** "today", "tomorrow", "in 6 days", "yesterday", "6 days ago", or a plain date beyond 60 days. */
  text: string;
  /** Short date for a parenthesis: "Fri 18 Sep" within 14 days, else "18 Sep"; the year only when it differs from the demo year. */
  short: string;
  /** Always complete, for a tooltip: "Fri 18 Sep 2026". */
  absolute: string;
  /** text plus the short date: "in 6 days (Fri 18 Sep)"; just the plain date beyond 60 days. */
  long: string;
}

function utcParts(dateStr: string): { y: number; m: number; d: number; wd: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr);
  if (!m) return null;
  const t = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  if (Number.isNaN(t.getTime())) return null;
  return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate(), wd: t.getUTCDay() };
}

/** "12 Sep 2026" for the demo-clock chip. */
export function formatDemoDate(now: Date): string {
  return `${now.getUTCDate()} ${MONTHS[now.getUTCMonth()]} ${now.getUTCFullYear()}`;
}

/** Null when `dateStr` is not a date. */
export function relativeDate(dateStr: string | undefined | null, now: Date = new Date()): RelativeDate | null {
  if (!dateStr) return null;
  const p = utcParts(dateStr);
  if (!p) return null;
  const days = daysUntil(dateStr.slice(0, 10), now);
  const demoYear = now.getUTCFullYear();
  const plain = `${p.d} ${MONTHS[p.m]}${p.y !== demoYear ? ` ${p.y}` : ""}`;
  const withWeekday = Math.abs(days) <= WEEKDAY_LIMIT_DAYS ? `${WEEKDAYS[p.wd]} ${plain}` : plain;
  const absolute = `${WEEKDAYS[p.wd]} ${p.d} ${MONTHS[p.m]} ${p.y}`;
  const n = Math.abs(days);
  const rel =
    days === 0 ? "today" : days === 1 ? "tomorrow" : days === -1 ? "yesterday" : days > 0 ? `in ${n} days` : `${n} days ago`;
  if (n > RELATIVE_DATE_LIMIT_DAYS) {
    return { days, text: plain, short: plain, absolute, long: plain };
  }
  return { days, text: rel, short: withWeekday, absolute, long: `${rel} (${withWeekday})` };
}

/** "12 Sep" from an ISO date (no year, no weekday): the x labels of a chart. Falls back to the input. */
export function dayMonth(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const p = utcParts(dateStr);
  return p ? `${p.d} ${MONTHS[p.m]}` : dateStr;
}

/** Elapsed time for people (design_spec.md 8.3): "5 s", "1 min 5 s", "2 min". Whole seconds above
 * ten, one decimal below ("0.4 s"); never "0.09 min". */
export function formatDuration(totalSeconds: number | undefined | null): string {
  if (totalSeconds === undefined || totalSeconds === null || !Number.isFinite(totalSeconds) || totalSeconds < 0) return "–";
  if (totalSeconds < 10) {
    const rounded = Math.round(totalSeconds * 10) / 10;
    return Number.isInteger(rounded) ? `${rounded} s` : `${rounded.toFixed(1)} s`;
  }
  const whole = Math.round(totalSeconds);
  if (whole < 60) return `${whole} s`;
  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  return seconds === 0 ? `${minutes} min` : `${minutes} min ${seconds} s`;
}

/** A whole number with Indian digit grouping (1,23,456), for counts and units next to rupee amounts. */
export function count(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "0";
  return Math.round(value).toLocaleString("en-IN");
}
