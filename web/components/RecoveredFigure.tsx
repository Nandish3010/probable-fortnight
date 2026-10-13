"use client";

import { inr, inrSigned } from "../lib/format";
import { useEffect, useState } from "react";
import { countUpValue, useCountUp } from "../lib/countUp";
import { prefersReducedMotion } from "../lib/motion";
import type { PlayImpact } from "../lib/impact";
import { BasisTag } from "./BasisTag";
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
  countOnce = false,
}: {
  impact: PlayImpact;
  testId?: string;
  countUp?: CountUpOptions;
  /** Omit for no chip at all (the decision card); true/false to show it / keep its space reserved. */
  chip?: boolean;
  /** A visual count-up, once, 600 ms, for a projected number that is not yet on a LIVE or REPLAY
   * panel (the landing's decision card). The settled figure is in the DOM text from the first
   * render; the count is drawn by an aria-hidden copy laid over it. Nothing runs under reduced motion. */
  countOnce?: boolean;
}) {
  const target = impact.recovered_inr;
  const value = useCountUp(target, countUp?.run ?? false, countUp?.delayMs ?? 0, countUp?.durationMs ?? 0);
  const running = Boolean(countUp?.run) && value !== target;
  const shown = countUp ? value : target;
  const positive = Math.round(target) > 0;

  const [ghost, setGhost] = useState<number | null>(() => (countOnce && !prefersReducedMotion() && target > 0 ? 0 : null));
  useEffect(() => {
    if (!countOnce || prefersReducedMotion() || !(target > 0)) {
      setGhost(null);
      return;
    }
    const DURATION_MS = 600;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const elapsed = now - start;
      if (elapsed >= DURATION_MS) {
        setGhost(null);
        return;
      }
      setGhost(countUpValue(target, elapsed, DURATION_MS));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [countOnce, target]);

  return (
    <div className={styles.figure} data-testid={testId}>
      <p className={styles.headline}>
        Recovered vs doing nothing{" "}
        {/* The count-up is decoration: the settled figure is announced once, by the panel's live region. */}
        <span className={styles.amountWrap}>
          <strong
            className={`${styles.amount} ${ghost !== null ? styles.amountCounting : ""} num`}
            aria-hidden={running ? true : undefined}
            data-testid={`${testId}-amount`}
          >
            {inrSigned(shown)}
          </strong>
          {ghost !== null ? (
            <strong className={`${styles.amount} ${styles.ghost} num`} aria-hidden="true" data-testid={`${testId}-count`}>
              {inrSigned(ghost)}
            </strong>
          ) : null}
        </span>
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
        <BasisTag basis="assumption" />{" "}
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
