"use client";

import { heroProofData } from "../lib/heroProof";
import type { Gap, Play } from "../lib/types";
import { Basis, BasisTag } from "./BasisTag";
import styles from "./HeroProof.module.css";

/** The landing's first screen, in one block under the "what Taal is" sentence: the projected figure with its
 * tags and the margin over a blanket markdown beside it (so a single video frame carries the claim and its
 * label). The figure never counts; it is final text from the first frame and only fades in (the same
 * rule as components/RecoveredFigure.tsx). The user line above it lives in the page (hero-subline). */
export function HeroProof({ gap, play, now }: { gap: Gap | null; play: Play | null; now?: Date }) {
  const { recovered, beat } = heroProofData(gap, play, now);
  return (
    <div className={styles.proof} data-testid="preview-figure">
      <Basis kind="projected" tag="none" className={styles.row}>
        <strong className={`${styles.amount} num`} data-testid="preview-figure-amount">
          {recovered}
        </strong>
        <span className={styles.tags}>
          <BasisTag basis="projected" />
          <BasisTag basis="synthetic" />
        </span>
        {beat ? (
          <span className={styles.beat} data-testid="hero-beat">
            {beat}
          </span>
        ) : null}
        <span className={styles.honesty}>Recovered against doing nothing. A projection, not a measurement.</span>
      </Basis>
    </div>
  );
}
