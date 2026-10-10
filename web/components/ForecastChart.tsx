"use client";

import { useEffect, useRef, useState } from "react";
import { chartSummary, separate, yTicks } from "../lib/chartScale";
import { dayMonth } from "../lib/format";
import type { Forecast } from "../lib/types";
import styles from "./ForecastChart.module.css";

const DEFAULT_WIDTH = 560;
const TICK_COUNT_LABEL_W = 52; // left margin: three tick labels and the rotated axis title
const PAD = { top: 34, bottom: 30, left: TICK_COUNT_LABEL_W, right: 14 };
const LABEL_H = 12; // the SVG is drawn 1:1 with CSS pixels, so every label is 12 px at its rendered size

const tickText = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

/**
 * Inline SVG line chart (no chart library): the demand forecast without the play (dashed) and with
 * it (solid), the offer window shaded and the extra units the play adds shaded between the lines.
 *
 * The SVG is drawn at the container's measured pixel width (a ResizeObserver; 560 before the first
 * measurement and on the server), so one user unit is one CSS pixel and the 12 px labels are 12 px on
 * screen. With `animate` the lines and areas play the Approve sequence (design_spec.md 6.2): the
 * baseline fades in, the play line draws over 700 ms, the lift area fades in. The container keeps
 * its height from the first render, so nothing moves when it mounts.
 */
export function ForecastChart({ forecast, animate = false }: { forecast: Forecast; animate?: boolean }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const read = () => {
      const w = Math.floor(el.getBoundingClientRect().width);
      if (w > 0) setMeasured((prev) => (prev === w ? prev : w));
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const series = forecast.series;

  if (series.length === 0) {
    return <p className="muted">No forecast series returned.</p>;
  }
  // One point cannot make a line, and the x scale below divides by (length - 1).
  if (series.length < 2) {
    return <p className="muted" data-testid="forecast-chart-empty">Not enough forecast points to draw a chart.</p>;
  }

  const width = Math.max(240, measured ?? DEFAULT_WIDTH);
  const height = width < 480 ? 250 : 280;
  const innerW = width - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;

  const maxV = Math.max(...series.flatMap((p) => [p.baseline_p50, p.play_p50]));
  const { ticks, top } = yTicks(maxV * 1.1);
  const x = (i: number) => PAD.left + (i / (series.length - 1)) * innerW;
  const y = (v: number) => PAD.top + innerH - (v / top) * innerH;

  const line = (pick: (p: (typeof series)[number]) => number) =>
    series.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(pick(p)).toFixed(1)}`).join(" ");
  const baselinePath = line((p) => p.baseline_p50);
  const playPath = line((p) => p.play_p50);
  const liftPath =
    series.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.play_p50).toFixed(1)}`).join(" ") +
    " " +
    [...series]
      .map((p, i) => ({ p, i }))
      .reverse()
      .map(({ p, i }) => `L${x(i).toFixed(1)},${y(p.baseline_p50).toFixed(1)}`)
      .join(" ") +
    " Z";

  // The offer window: from the first date inside it to the last.
  const startIdx = Math.max(0, series.findIndex((p) => p.date >= forecast.play_window.start));
  let endIdx = series.length - 1;
  for (let i = series.length - 1; i >= 0; i -= 1) {
    if (series[i].date <= forecast.play_window.end) {
      endIdx = i;
      break;
    }
  }
  if (endIdx <= startIdx) endIdx = Math.min(series.length - 1, startIdx + 1);
  const hasWindow = series.findIndex((p) => p.date >= forecast.play_window.start) >= 0;
  const winX = x(startIdx);
  const winW = Math.max(8, x(endIdx) - winX);

  // Direct labels, each placed clear of its own line: the play's above the highest it gets under
  // the label, the baseline's below the lowest it gets, both starting at the window's left edge.
  const labelSpan = Math.max(1, Math.ceil(120 / (innerW / (series.length - 1))));
  const spanEnd = Math.min(series.length - 1, startIdx + labelSpan);
  const slice = series.slice(startIdx, spanEnd + 1);
  const playLabelY = y(Math.max(...slice.map((p) => p.play_p50))) - 8;
  const baseLabelY = y(Math.min(...slice.map((p) => p.baseline_p50))) + 8 + LABEL_H;
  const [playY, baseY] = separate(playLabelY, baseLabelY, LABEL_H + 4);
  const labelX = winX + 6;

  // The lift label sits right of the window, with a short leader to the shaded area.
  let peak = startIdx;
  for (let i = startIdx; i <= endIdx; i += 1) {
    if (series[i].play_p50 - series[i].baseline_p50 > series[peak].play_p50 - series[peak].baseline_p50) peak = i;
  }
  const hasLift = series[peak].play_p50 - series[peak].baseline_p50 > 0.05;
  const peakMidY = (y(series[peak].play_p50) + y(series[peak].baseline_p50)) / 2;
  const liftX = Math.min(x(endIdx) + 18, width - 150);
  const liftY = peakMidY - 6;

  const summary = chartSummary(series, forecast.play_window.start, forecast.play_window.end);
  const motion = animate ? styles.animate : "";

  return (
    <div ref={wrapRef} className={`${styles.wrap} ${motion}`} style={{ minHeight: height }} data-testid="forecast-chart">
      <svg
        role="img"
        aria-label={summary}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={`forecast-chart ${styles.chart}`}
      >
        {/* Chromium's SVG accessibility mapping does not prune a role="img" element's own
           descendants: without this, every <text> label below is still exposed as the img node's
           accessible content, alongside its aria-label. aria-hidden on one wrapping <g> makes the
           aria-label the chart's only accessible content (tests/e2e/live-regions.spec.ts). */}
        <g aria-hidden="true">
          {hasWindow ? <rect x={winX} y={PAD.top} width={winW} height={innerH} className={styles.window} data-testid="chart-window" /> : null}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className={t === 0 ? styles.axis : styles.grid} />
              <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end" className={styles.label}>
                {tickText(t)}
              </text>
            </g>
          ))}
          <text transform={`translate(12 ${PAD.top + innerH / 2}) rotate(-90)`} textAnchor="middle" className={styles.label}>
            Units per day
          </text>

          {hasWindow ? (
            <text x={winX} y={PAD.top - 10} className={styles.label}>
              Offer window
            </text>
          ) : null}

          <path d={liftPath} className={`${styles.lift} ${styles.liftIn}`} />
          <path d={baselinePath} className={`${styles.line} ${styles.baseline} ${styles.baselineIn}`} />
          <path d={playPath} pathLength={1} className={`${styles.line} ${styles.play} ${styles.playIn}`} />

          <text x={labelX} y={playY} className={`${styles.label} ${styles.labelPlay} ${styles.labelIn}`}>
            With the play
          </text>
          <text x={labelX} y={baseY} className={`${styles.label} ${styles.labelBase} ${styles.labelIn}`}>
            Without the play
          </text>

          {hasLift ? (
            <g className={styles.labelIn}>
              <line x1={liftX - 4} y1={liftY + 4} x2={x(peak)} y2={peakMidY} className={styles.leader} />
              <circle cx={x(peak)} cy={peakMidY} r={3} className={styles.leaderDot} />
              <text x={liftX} y={liftY} className={`${styles.label} ${styles.labelPlay}`}>
                Extra units sold
              </text>
              <text x={liftX} y={liftY + LABEL_H + 2} className={`${styles.label} ${styles.labelPlay}`}>
                because of the play
              </text>
            </g>
          ) : null}

          <text x={PAD.left} y={height - 8} className={styles.label}>
            {dayMonth(series[0].date)}
          </text>
          <text x={width - PAD.right} y={height - 8} textAnchor="end" className={styles.label}>
            {dayMonth(series[series.length - 1].date)}
          </text>
        </g>
      </svg>
    </div>
  );
}
