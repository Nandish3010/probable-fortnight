import { inr } from "../lib/format";
import type { Counterfactuals, ExpectedOutcome, Holdout } from "../lib/types";

export function CounterfactualBars({
  counterfactuals,
  expectedOutcome,
  holdout,
}: {
  counterfactuals: Counterfactuals;
  expectedOutcome: ExpectedOutcome;
  holdout?: Holdout;
}) {
  const rows = [
    { label: "Do nothing", value: counterfactuals.do_nothing_inr, cls: "bar--danger" },
    { label: `Blanket markdown (${counterfactuals.blanket_markdown_pct}%)`, value: counterfactuals.blanket_markdown_inr, cls: "bar--warn" },
    { label: "This play", value: expectedOutcome.discount_cost_inr, cls: "bar--good" },
  ];
  const max = Math.max(...rows.map((r) => r.value), 1);
  const holdoutValue = holdout ? expectedOutcome.discount_cost_inr * holdout.fraction : 0;

  return (
    <div className="counterfactuals">
      {rows.map((row) => (
        <div className="counterfactuals__row" key={row.label}>
          <span className="counterfactuals__label">{row.label}</span>
          <div className="counterfactuals__track">
            <div
              className={`counterfactuals__bar ${row.cls}`}
              style={{ width: `${Math.max(4, (row.value / max) * 100)}%` }}
            />
          </div>
          <span className="counterfactuals__value">{inr(row.value)}</span>
        </div>
      ))}
      {holdout ? (
        <div className="counterfactuals__row counterfactuals__row--holdout">
          <span className="counterfactuals__label">Holdout ({Math.round(holdout.fraction * 100)}%)</span>
          <div className="counterfactuals__track">
            <div
              className="counterfactuals__bar bar--holdout"
              style={{ width: `${Math.max(4, (holdoutValue / max) * 100)}%` }}
            />
          </div>
          <span className="counterfactuals__value">{inr(holdoutValue)}</span>
        </div>
      ) : null}
    </div>
  );
}
