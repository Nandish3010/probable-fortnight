import type { Forecast } from "../lib/types";

// Inline SVG line chart: baseline_p50 vs play_p50 (no chart library, per spec).
export function ForecastChart({ forecast }: { forecast: Forecast }) {
  const width = 640;
  const height = 220;
  const padTop = 16;
  const padBottom = 28;
  const padLeft = 16;
  const padRight = 16;
  const series = forecast.series;

  if (series.length === 0) {
    return <p className="muted">No forecast series returned.</p>;
  }

  const values = series.flatMap((p) => [p.baseline_p50, p.play_p50, p.p10 ?? p.baseline_p50, p.p90 ?? p.play_p50]);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const spanV = maxV - minV || 1;
  const innerW = width - padLeft - padRight;
  const innerH = height - padTop - padBottom;

  const x = (i: number) => padLeft + (i / (series.length - 1)) * innerW;
  const y = (v: number) => padTop + innerH - ((v - minV) / spanV) * innerH;

  const baselinePath = series.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.baseline_p50).toFixed(1)}`).join(" ");
  const playPath = series.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.play_p50).toFixed(1)}`).join(" ");

  const windowStartIdx = series.findIndex((p) => p.date >= forecast.play_window.start);
  const windowX = windowStartIdx >= 0 ? x(windowStartIdx) : null;

  const firstDate = series[0]?.date ?? "";
  const lastDate = series[series.length - 1]?.date ?? "";

  return (
    <svg
      role="img"
      aria-label="Forecast chart: baseline versus play-aware demand"
      viewBox={`0 0 ${width} ${height}`}
      className="forecast-chart"
      preserveAspectRatio="xMidYMid meet"
    >
      {windowX !== null ? (
        <rect
          x={windowX}
          y={padTop}
          width={width - padRight - windowX}
          height={innerH}
          className="forecast-chart__window"
        />
      ) : null}
      <line x1={padLeft} y1={padTop + innerH} x2={width - padRight} y2={padTop + innerH} className="forecast-chart__axis" />
      <path d={baselinePath} className="forecast-chart__line forecast-chart__line--baseline" />
      <path d={playPath} className="forecast-chart__line forecast-chart__line--play" />
      <line x1={padLeft} y1={padTop + 8} x2={padLeft + 18} y2={padTop + 8} className="forecast-chart__line forecast-chart__line--baseline" />
      <text x={padLeft + 22} y={padTop + 11} className="forecast-chart__label">baseline p50</text>
      <line x1={padLeft + 110} y1={padTop + 8} x2={padLeft + 128} y2={padTop + 8} className="forecast-chart__line forecast-chart__line--play" />
      <text x={padLeft + 132} y={padTop + 11} className="forecast-chart__label">with play (units/day)</text>
      <text x={padLeft} y={height - 6} className="forecast-chart__label">{firstDate}</text>
      <text x={width - padRight} y={height - 6} textAnchor="end" className="forecast-chart__label">{lastDate}</text>
    </svg>
  );
}
