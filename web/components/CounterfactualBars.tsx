import { inr } from "../lib/format";
import type { Counterfactuals, ExpectedOutcome } from "../lib/types";

/** `₹-8,423` from `inr()` reads worse than `-₹8,423`; move the sign in front of the symbol. */
function signedInr(value: number): string {
  const s = inr(Math.abs(value));
  return value < 0 ? `-${s}` : s;
}

interface Segment {
  key: string;
  label: string;
  value: number; // signed; negative = margin destroyed/written off, positive = margin earned
  cls: string;
}

interface Row {
  key: string;
  label: string;
  segments: Segment[];
  net: number;
}

export function CounterfactualBars({
  counterfactuals,
  expectedOutcome,
  blanketMarkdownGiveawayInr,
}: {
  counterfactuals: Counterfactuals;
  expectedOutcome: ExpectedOutcome;
  /** Optional: the margin the blanket markdown gives away on volume that was projected to sell
   * at full price anyway (docs/impact_math.md, Part 1.2). Only known for plays where the baseline
   * forecast has been worked out ahead of time; when absent, the blanket-markdown bar renders as
   * one segment instead of two -- still on the same axis, just without that decomposition. */
  blanketMarkdownGiveawayInr?: number;
}) {
  // Every option is reduced to the same thing: margin actually earned, minus the cost of whatever
  // part of the lot still gets written off. do_nothing_inr and waste_avoided_inr are both already
  // priced at unit_cost, so (do_nothing_inr - waste_avoided_inr) is the play's residual write-off
  // without needing unit_cost or units_at_risk client-side (docs/impact_math.md, Part 1.2).
  const residualWriteoffPlay = counterfactuals.do_nothing_inr - expectedOutcome.waste_avoided_inr;
  const marginEarnedPlay = expectedOutcome.margin_inr;

  const blanketSegments: Segment[] =
    blanketMarkdownGiveawayInr != null
      ? [
          { key: "giveaway", label: "given away on volume that would have sold anyway", value: -blanketMarkdownGiveawayInr, cls: "seg--destroyed" },
          { key: "writeoff", label: "residual write-off", value: -(counterfactuals.blanket_markdown_inr - blanketMarkdownGiveawayInr), cls: "seg--writeoff" },
        ]
      : [{ key: "writeoff", label: "margin destroyed", value: -counterfactuals.blanket_markdown_inr, cls: "seg--writeoff" }];

  const rows: Row[] = [
    {
      key: "do_nothing",
      label: "Do nothing",
      segments: [{ key: "writeoff", label: "written off", value: -counterfactuals.do_nothing_inr, cls: "seg--writeoff" }],
      net: -counterfactuals.do_nothing_inr,
    },
    {
      key: "blanket_markdown",
      label: `Blanket markdown (${counterfactuals.blanket_markdown_pct}%)`,
      segments: blanketSegments,
      net: -counterfactuals.blanket_markdown_inr,
    },
    {
      key: "play",
      label: "This play",
      segments: [
        { key: "margin", label: "margin earned", value: marginEarnedPlay, cls: "seg--earned" },
        { key: "writeoff", label: "residual write-off", value: -residualWriteoffPlay, cls: "seg--writeoff" },
      ],
      net: marginEarnedPlay - residualWriteoffPlay,
    },
  ];

  const maxMagnitude = Math.max(
    counterfactuals.do_nothing_inr,
    counterfactuals.blanket_markdown_inr,
    residualWriteoffPlay,
    marginEarnedPlay,
    1,
  );

  return (
    <div className="counterfactuals">
      <p className="counterfactuals__axis-label">
        Net margin retained (₹) -- a projection from the estimator, not a measurement. Right of
        the line is margin earned; left is margin destroyed or written off.
      </p>
      {rows.map((row) => (
        <div className="counterfactuals__row counterfactuals__row--diverging" key={row.key}>
          <span className="counterfactuals__label">{row.label}</span>
          <div className="counterfactuals__diverging-track">
            <div className="counterfactuals__zero-line" />
            {row.segments.map((seg) => {
              const widthPct = Math.min(50, (Math.abs(seg.value) / maxMagnitude) * 50);
              const side = seg.value < 0 ? "left" : "right";
              return (
                <div
                  key={seg.key}
                  className={`counterfactuals__segment ${seg.cls} counterfactuals__segment--${side}`}
                  style={{ width: `${widthPct}%` }}
                  title={`${seg.label}: ${signedInr(seg.value)}`}
                />
              );
            })}
          </div>
          <span className={`counterfactuals__value ${row.net < 0 ? "counterfactuals__value--neg" : "counterfactuals__value--pos"}`}>
            {signedInr(row.net)}
          </span>
        </div>
      ))}
      <ul className="counterfactuals__legend">
        <li><span className="counterfactuals__swatch seg--earned" /> margin earned</li>
        <li><span className="counterfactuals__swatch seg--destroyed" /> given away on volume that would have sold anyway</li>
        <li><span className="counterfactuals__swatch seg--writeoff" /> write-off</li>
      </ul>
    </div>
  );
}
