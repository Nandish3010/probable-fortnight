"use client";

import { inr, inrSigned } from "../lib/format";
import type { PlayImpact } from "../lib/impact";
import { Basis, BasisTag } from "./BasisTag";
import { Icon } from "./icons";
import styles from "./RecoveredFigure.module.css";

/** The canonical figure (ux_plan.md section 2): "Recovered vs doing nothing ₹X" with the two parts
 * it is made of. Every screen that states the play's impact renders this, from playImpact().
 *
 * On the Approve result it can also show the green delta chip ("+₹X vs doing nothing", `chip`):
 * the chip's space is always reserved, so it fades in with no layout shift.
 *
 * The figure never counts. Its final text is in the DOM and on screen from the first frame (a
 * count would put wrong-looking intermediate numbers in front of a viewer or a screen recording);
 * `fade` only brings it in with a short opacity fade, which prefers-reduced-motion switches off. */
export function RecoveredFigure({
  impact,
  testId = "recovered-figure",
  chip,
  fade = false,
  atStakeAbove = false,
}: {
  impact: PlayImpact;
  testId?: string;
  /** Omit for no chip at all (the decision card); true/false to show it / keep its space reserved. */
  chip?: boolean;
  /** Fade the figure in once (<= 200 ms, opacity only) as it appears. The text is already final. */
  fade?: boolean;
  /** The card prints the gap's "rupees at stake" sentence just above this figure. Its SYNTHETIC tag
   * sits here, beside PROJECTED, so the card carries one pair of tags and no extra line. */
  atStakeAbove?: boolean;
}) {
  const target = impact.recovered_inr;
  const positive = Math.round(target) > 0;

  return (
    <Basis kind="projected" tag="none" className={styles.figure} data-testid={testId}>
      <p className={styles.headline}>
        Recovered vs doing nothing{" "}
        <strong className={`${styles.amount} ${fade ? styles.fade : ""} num`} data-testid={`${testId}-amount`}>
          {inrSigned(target)}
        </strong>
      </p>
      {chip !== undefined ? (
        <span
          className={`${styles.chip} ${chip ? styles.chipOn : ""} ${positive ? "" : styles.chipNeutral}`}
          data-testid={`${testId}-delta`}
          aria-hidden={chip ? undefined : true}
        >
          {positive ? <Icon name="trending-up" size={16} /> : null}
          {positive ? "+" : ""}
          {inrSigned(target)} vs doing nothing
        </span>
      ) : null}
      <p className={styles.parts} data-testid={`${testId}-parts`}>
        {/* Every figure here is projected from the estimator; "measured" appears only on Outcomes, from the holdout. */}
        {atStakeAbove ? (
          <>
            <BasisTag basis="synthetic" />{" "}
          </>
        ) : null}
        <BasisTag basis="projected" />{" "}
        {impact.components.map((c, i) => (
          <span key={c.label}>
            {i > 0 ? (c.inr < 0 ? " minus " : " plus ") : ""}
            {c.label.toLowerCase()} {inr(Math.abs(c.inr))}
          </span>
        ))}
      </p>
    </Basis>
  );
}
