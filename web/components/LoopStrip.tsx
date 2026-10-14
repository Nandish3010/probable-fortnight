import { STEPS } from "../lib/progress";
import styles from "./LoopStrip.module.css";

/** The Taal loop as one line under the hero subline, at every width: the stepper's own stage names
 * (lib/progress.ts STEPS: Spot, Plan, Approve, Offer, Measure) and the return arrow. Not interactive;
 * the stepper in the nav is the navigation and public/loop.svg (below the decision on a desktop) is the
 * detailed version. It is one image to a screen reader, whose label reads the whole loop. */
export function LoopStrip() {
  const names = STEPS.map((s) => s.label);
  const label = `The Taal loop: ${names.join(", ")}, then what Measure finds updates the priors and the loop starts again.`;
  return (
    <p className={styles.strip} role="img" aria-label={label} data-testid="loop-strip">
      {names.map((n, i) => (
        <span key={n} className={styles.item}>
          <span className={styles.name}>{n}</span>
          {i < names.length - 1 ? <span className={styles.arrow}>{"→"}</span> : null}
        </span>
      ))}
      <span className={styles.item}>
        <span className={styles.arrow}>{"↺"}</span>
        <span className={styles.back}>priors update</span>
      </span>
    </p>
  );
}
