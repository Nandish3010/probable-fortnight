import { Icon } from "./icons";
import { STEPS } from "../lib/progress";
import styles from "./LoopCompact.module.css";

/** The Taal loop as a row of words, for a phone: public/loop.svg is too small to read there and is
 * not shown at 640 px and below, so this carries the same story in the stepper's own stage names
 * (lib/progress.ts STEPS: Spot, Plan, Approve, Offer, Measure). From 641 px up the SVG is the loop
 * and this is not shown. Text, not a link: the stepper in the nav is the navigation. */
export function LoopCompact() {
  return (
    <figure className={styles.loop} data-testid="loop-compact">
      <figcaption className={styles.caption}>The loop</figcaption>
      <ol className={styles.steps} aria-label="The Taal loop in five steps, then back to the start">
        {STEPS.map((step, i) => (
          <li key={step.id} className={styles.step}>
            <span>{step.label}</span>
            {i < STEPS.length - 1 ? (
              <span className={styles.arrow} aria-hidden="true">
                <Icon name="arrow-right" size={14} />
              </span>
            ) : null}
          </li>
        ))}
      </ol>
      <p className={styles.note}>What Measure finds updates the next forecast, and the loop starts again.</p>
    </figure>
  );
}
