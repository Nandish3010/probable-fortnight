"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Icon } from "./icons";
import { STEPS, stepAccessibleName, stepViews, type Progress, type StepId } from "../lib/progress";
import { startProgress, useProgress } from "../lib/progressStore";
import styles from "./Stepper.module.css";

/** The five-step loop as navigation: Spot, Plan, Approve, Offer, Measure (design_spec.md section 7).
 * Every step is a link to its screen, and none is ever disabled: a locked step stays a link and
 * only says what is missing ("Approve first"). Ticks come from lib/progress.ts, read from the
 * sandbox and this browser's crumbs, never from the server's own bookkeeping.
 *
 * `current` is the step whose screen is open. `progress` can be passed to render a fixed state (the
 * dev page, tests); without it the component mounts the shared progress store and follows it. */
export function Stepper({ current, progress }: { current: StepId | null; progress?: Progress }) {
  const live = useProgress();
  useEffect(() => {
    if (!progress) startProgress();
  }, [progress, current]);

  const p = progress ?? live.progress;
  const views = stepViews(current, p);

  return (
    <nav aria-label="Progress" className={styles.stepper} data-testid="stepper">
      <ol className={styles.list}>
        {STEPS.map((step, i) => {
          const view = views[i];
          const title = view.state === "locked" && view.hint ? view.hint : `${step.label}: ${step.destination}`;
          return (
            <li key={step.id} className={styles.item} data-step={step.id} data-state={view.state} data-done={view.done ? "true" : "false"}>
              <Link
                href={step.href}
                className={styles.link}
                aria-current={view.state === "current" ? "step" : undefined}
                aria-label={stepAccessibleName(step, view)}
                title={title}
                data-tour={step.id === "offer" ? "step-offer" : undefined}
              >
                <span className={styles.dot} data-part="dot" aria-hidden="true">
                  {view.state === "done" || (view.state === "current" && view.done) ? (
                    <Icon name="check" size={14} />
                  ) : view.state === "locked" ? (
                    <Icon name="lock" size={12} />
                  ) : (
                    i + 1
                  )}
                </span>
                <span className={styles.text}>
                  <span className={styles.label} data-part="label">{step.label}</span>
                  <span className={styles.caption} data-part="caption">{view.state === "locked" && view.shortHint ? view.shortHint : step.persona}</span>
                </span>
              </Link>
              {i < STEPS.length - 1 ? <span className={styles.connector} aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
