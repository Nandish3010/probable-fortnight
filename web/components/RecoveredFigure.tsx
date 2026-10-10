"use client";

import { inr, inrSigned } from "../lib/format";
import { useCountUp } from "../lib/countUp";
import type { PlayImpact } from "../lib/impact";
import { Icon } from "./icons";
import styles from "./RecoveredFigure.module.css";

/** The count-up on the Approve result: the amount runs from 0 to the canonical figure. */
export interface CountUpOptions {
  /** True while the count runs (the "animating" phase); false shows the figure at once. */
  run: boolean;
  delayMs: number;
  durationMs: number;
}

/** The canonical figure (ux_plan.md section 2): "Recovered vs doing nothing ₹X" with the two parts
 * it is made of. Every screen that states the play's impact renders this, from playImpact().
 *
 * On the Approve result it can also count up (`countUp`) and show the green delta chip
 * ("+₹X vs doing nothing", `chip`): the chip's space is always reserved, so it fades in with no
 * layout shift. */
export function RecoveredFigure({
  impact,
  testId = "recovered-figure",
  countUp,
  chip,
}: {
  impact: PlayImpact;
  testId?: string;
  countUp?: CountUpOptions;
  /** Omit for no chip at all (the decision card); true/false to show it / keep its space reserved. */
  chip?: boolean;
}) {
  const target = impact.recovered_inr;
  const value = useCountUp(target, countUp?.run ?? false, countUp?.delayMs ?? 0, countUp?.durationMs ?? 0);
  const running = Boolean(countUp?.run) && value !== target;
  const shown = countUp ? value : target;
  const positive = Math.round(target) > 0;

  return (
    <div className={styles.figure} data-testid={testId}>
      <p className={styles.headline}>
        Recovered vs doing nothing{" "}
        {/* The count-up is decoration: the settled figure is announced once, by the panel's live region. */}
        <strong className={`${styles.amount} num`} aria-hidden={running ? true : undefined} data-testid={`${testId}-amount`}>
          {inrSigned(shown)}
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
        {impact.components.map((c, i) => (
          <span key={c.label}>
            {i > 0 ? (c.inr < 0 ? " minus " : " plus ") : ""}
            {c.label.toLowerCase()} {inr(Math.abs(c.inr))}
          </span>
        ))}
      </p>
    </div>
  );
}
