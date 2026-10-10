// Pure helpers for components/ForecastChart.tsx: a "nice" y axis with three ticks, label
// separation, and the one-sentence text summary the chart carries as its accessible name.
import { dayMonth } from "./format";
import type { ForecastPoint } from "./types";

/** Rounds `v` up to 1, 2, 3, 4, 6, 8 or 10 times a power of ten, so a three-tick axis reads 0, half, top. */
export function niceCeil(v: number): number {
  if (!(v > 0)) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = Math.pow(10, exp);
  const f = v / base;
  const step = [1, 2, 3, 4, 6, 8, 10].find((s) => f <= s) ?? 10;
  return step * base;
}

/** Three y ticks, 0, half and the nice top, in data units. */
export function yTicks(maxValue: number): { ticks: [number, number, number]; top: number } {
  const top = niceCeil(maxValue * 1.04);
  return { ticks: [0, top / 2, top], top };
}

/** Two label baselines at least `gap` apart. The one that was higher stays higher. Used so the two
 * direct line labels never sit on top of each other where the lines are close. */
export function separate(yA: number, yB: number, gap: number): [number, number] {
  if (Math.abs(yA - yB) >= gap) return [yA, yB];
  const mid = (yA + yB) / 2;
  return yA <= yB ? [mid - gap / 2, mid + gap / 2] : [mid + gap / 2, mid - gap / 2];
}

const rounded = (v: number) => (Math.abs(v) >= 10 ? Math.round(v) : Math.round(v * 10) / 10);

/** The chart's accessible name: what the two lines do, in words. */
export function chartSummary(series: ForecastPoint[], windowStart?: string, windowEnd?: string): string {
  if (series.length < 2) return "Forecast chart: not enough points.";
  const first = series[0];
  const last = series[series.length - 1];
  let peak = series[0];
  for (const p of series) if (p.play_p50 - p.baseline_p50 > peak.play_p50 - peak.baseline_p50) peak = p;
  const extra = peak.play_p50 - peak.baseline_p50;
  const lift =
    extra > 0.05
      ? ` The play adds most on ${dayMonth(peak.date)}: ${rounded(peak.play_p50)} units a day with it against ${rounded(peak.baseline_p50)} without.`
      : " The two lines are the same: the play adds no units.";
  const win = windowStart && windowEnd ? ` The offer window runs ${dayMonth(windowStart)} to ${dayMonth(windowEnd)}.` : "";
  return `Forecast chart: units sold per day, ${dayMonth(first.date)} to ${dayMonth(last.date)}, without the play and with the play.${lift}${win}`;
}
