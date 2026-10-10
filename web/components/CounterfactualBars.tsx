import { inrSigned } from "../lib/format";
import { playImpact } from "../lib/impact";
import type { Counterfactuals, ExpectedOutcome, Mechanic } from "../lib/types";
import { InfoNote } from "./InfoNote";
import { RecoveredFigure } from "./RecoveredFigure";

interface Segment {
  key: string;
  label: string;
  value: number; // signed; negative = margin destroyed/written off, positive = margin earned
  cls: string;
  /** The legend entry this segment belongs to. Segments sharing one share its swatch. */
  legend: string;
}

interface Row {
  key: string;
  label: string;
  segments: Segment[];
  net: number;
}

// The legend names a colour once. Only the colours drawn for the rows on screen get an entry, and
// the transfer cost keeps its own entry (and its own hatched swatch), apart from the amber giveaway.
const LEGEND: Record<string, string> = {
  earned: "margin earned",
  giveaway: "given away on volume that would have sold anyway",
  transfer: "transfer cost",
  writeoff: "write-off",
};
const LEGEND_SWATCH: Record<string, string> = {
  earned: "seg--earned",
  giveaway: "seg--destroyed",
  transfer: "seg--transfer",
  writeoff: "seg--writeoff",
};

export function CounterfactualBars({
  counterfactuals,
  expectedOutcome,
  mechanic,
  atStakeInr,
  blanketMarkdownGiveawayInr,
  showFigure = true,
}: {
  counterfactuals: Counterfactuals;
  expectedOutcome: ExpectedOutcome;
  /** Decides how the play's bar is built: a transfer's margin already contains the waste it avoids. */
  mechanic: Mechanic | string;
  /** The gap's rupees at stake, for the "within noise" test; defaults to the do-nothing loss. */
  atStakeInr?: number;
  /** Optional: the margin the blanket markdown gives away on volume that was projected to sell
   * at full price anyway (docs/impact_math.md, Part 1.2). Only known for plays where the baseline
   * forecast has been worked out ahead of time; when absent, the blanket-markdown bar renders as
   * one segment instead of two -- still on the same axis, just without that decomposition. */
  blanketMarkdownGiveawayInr?: number;
  /** The decision card (PlayCard) shows the canonical figure itself, above the bars; it passes
   * false so the figure is not on the page twice. Outcomes and any bare use keep it. */
  showFigure?: boolean;
}) {
  // Every figure below comes from playImpact(), the one function the whole UI shares, so this
  // chart, the Approve result and the Outcomes example cannot disagree.
  const impact = playImpact({ mechanic, expected_outcome: expectedOutcome, counterfactuals }, { rupees_at_stake: atStakeInr });

  // do_nothing_inr and waste_avoided_inr are both priced at unit_cost, so (do_nothing - waste
  // avoided) is the lot the play still writes off, without needing unit_cost or units_at_risk here.
  const doNothingLoss = counterfactuals.do_nothing_inr;
  const residualWriteoffPlay = doNothingLoss - impact.waste_avoided_inr;
  const isTransfer = mechanic === "transfer_plus_nudge";

  const blanketSegments: Segment[] =
    blanketMarkdownGiveawayInr != null
      ? [
          { key: "giveaway", label: LEGEND.giveaway, value: -blanketMarkdownGiveawayInr, cls: "seg--destroyed", legend: "giveaway" },
          { key: "writeoff", label: "residual write-off", value: -(counterfactuals.blanket_markdown_inr - blanketMarkdownGiveawayInr), cls: "seg--writeoff", legend: "writeoff" },
        ]
      : [{ key: "writeoff", label: "margin destroyed", value: -counterfactuals.blanket_markdown_inr, cls: "seg--writeoff", legend: "writeoff" }];

  // A sales play earns margin on what it sells and still writes off the rest. A transfer's
  // "margin" is waste avoided minus the transfer cost, so its bar is the residual write-off plus
  // that cost (both left of the line); showing margin as a gain as well would count the avoided
  // waste twice (the old bar showed Tea at -19.8k; -27.5k is right).
  const playSegments: Segment[] = isTransfer
    ? [
        { key: "transfer", label: LEGEND.transfer, value: impact.margin_inr - impact.waste_avoided_inr, cls: "seg--transfer", legend: "transfer" },
        { key: "writeoff", label: "residual write-off", value: -residualWriteoffPlay, cls: "seg--writeoff", legend: "writeoff" },
      ]
    : [
        { key: "margin", label: LEGEND.earned, value: impact.margin_inr, cls: "seg--earned", legend: "earned" },
        { key: "writeoff", label: "residual write-off", value: -residualWriteoffPlay, cls: "seg--writeoff", legend: "writeoff" },
      ];

  const rows: Row[] = [
    {
      key: "do_nothing",
      label: "Do nothing",
      segments: [{ key: "writeoff", label: "written off", value: impact.do_nothing_inr, cls: "seg--writeoff", legend: "writeoff" }],
      net: impact.do_nothing_inr,
    },
    {
      key: "blanket_markdown",
      label: `Blanket markdown (${counterfactuals.blanket_markdown_pct}%)`,
      segments: blanketSegments,
      net: impact.blanket_inr,
    },
    {
      key: "play",
      label: "This play",
      segments: playSegments,
      net: impact.play_net_inr,
    },
  ];

  // Segments on the same side of the zero line stack outward from it (each starts where the
  // previous one ended). The axis is scaled to the longest side of any row.
  const sideTotal = (row: Row, side: "left" | "right") =>
    row.segments.filter((seg) => (seg.value < 0 ? "left" : "right") === side).reduce((sum, seg) => sum + Math.abs(seg.value), 0);
  const maxMagnitude = Math.max(...rows.flatMap((row) => [sideTotal(row, "left"), sideTotal(row, "right")]), 1);
  // "Recommended" only when the play really keeps the most of the three; otherwise the row is
  // highlighted (it is the one being decided) but not praised.
  // Legend entries for the segments actually drawn, in a fixed order.
  const drawn = new Set(rows.flatMap((row) => row.segments.filter((seg) => seg.value !== 0).map((seg) => seg.legend)));
  const legend = ["earned", "giveaway", "transfer", "writeoff"].filter((k) => drawn.has(k));
  const playIsBest = impact.play_net_inr >= Math.max(impact.do_nothing_inr, impact.blanket_inr);

  return (
    <div className="counterfactuals">
      {showFigure ? <RecoveredFigure impact={impact} testId="recovered-figure" /> : null}
      {rows.map((row) => (
        <div
          className={`counterfactuals__row counterfactuals__row--diverging${row.key === "play" ? " counterfactuals__row--play" : ""}`}
          key={row.key}
        >
          <span className="counterfactuals__label">
            {row.label}
            {row.key === "play" && playIsBest ? <span className="counterfactuals__tag">Recommended</span> : null}
          </span>
          <div className="counterfactuals__diverging-track">
            <div className="counterfactuals__zero-line" />
            {(() => {
              const offset = { left: 0, right: 0 };
              return row.segments.map((seg) => {
                const side = seg.value < 0 ? "left" : "right";
                const widthPct = (Math.abs(seg.value) / maxMagnitude) * 50;
                const start = 50 + offset[side];
                offset[side] += widthPct;
                return (
                  <div
                    key={seg.key}
                    className={`counterfactuals__segment ${seg.cls} counterfactuals__segment--${side}`}
                    style={{ width: `${widthPct}%`, [side === "left" ? "right" : "left"]: `${start}%` }}
                    title={`${seg.label}: ${inrSigned(seg.value)}`}
                  />
                );
              });
            })()}
          </div>
          <span className={`counterfactuals__value ${row.net < 0 ? "counterfactuals__value--neg" : "counterfactuals__value--pos"}`}>
            {inrSigned(row.net)}
          </span>
        </div>
      ))}
      <p className="counterfactuals__comparison" data-testid="comparison-line">{impact.comparison.copy}</p>
      <InfoNote
        testId="bars-info"
        label="About these bars"
        lead={
          <ul className="counterfactuals__legend" data-testid="bars-legend">
            {legend.map((k) => (
              <li key={k} data-legend={k}>
                <span className={`counterfactuals__swatch ${LEGEND_SWATCH[k]}`} /> {LEGEND[k]}
              </li>
            ))}
          </ul>
        }
      >
        <span id="counterfactuals-axis">
          Net margin retained (₹) - a projection from the estimator, not a measurement. Right of the line is margin
          earned; left is margin destroyed or written off.
        </span>
      </InfoNote>
    </div>
  );
}
