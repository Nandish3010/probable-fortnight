"use client";

import { APPROVE_STEPS, formatElapsed, workingCopy } from "../lib/approveMachine";
import { Icon } from "./icons";
import styles from "./ApproveSteps.module.css";

/**
 * The three things Approve does, shown honestly (design_spec.md 6.2). The backend answers once, so
 * while the request is in flight all three are "working" with the same pulsing dot: ticking them
 * one by one before the answer would be a fake progress bar. When the answer arrives (`ticked`
 * counts up in a short stagger) each gets its tick, then the list folds into one summary line.
 */
export function ApproveSteps({
  ticked,
  collapsed,
  seconds,
  elapsedMs,
}: {
  /** 0 while waiting; 1 to 3 as the response's ticks land. */
  ticked: number;
  collapsed: boolean;
  /** Whole seconds waited so far (from performance.now(), not an interval counter). */
  seconds: number;
  /** Click to response, once known. */
  elapsedMs: number | null;
}) {
  const waiting = elapsedMs === null;
  return (
    <div className={styles.steps} data-testid="approve-steps" data-collapsed={collapsed ? "true" : "false"}>
      <div className={`${styles.fold} ${collapsed ? styles.folded : ""}`} inert={collapsed ? true : undefined}>
        <div className={styles.foldInner}>
          <ol className={styles.list}>
            {APPROVE_STEPS.map((label, i) => {
              const done = i < ticked;
              return (
                <li key={label} className={styles.item} data-state={done ? "done" : "working"} data-testid="approve-step">
                  <span className={`${styles.mark} ${done ? styles.markDone : ""}`} aria-hidden="true">
                    {done ? <Icon name="check" size={14} /> : <span className={styles.dot} />}
                  </span>
                  <span className={styles.label}>{label}</span>
                  <span className={styles.state}>{done ? "done" : "working"}</span>
                </li>
              );
            })}
          </ol>
          {waiting ? (
            <p className={styles.timer} data-testid="approve-timer" aria-hidden="true">
              {workingCopy(seconds)}
            </p>
          ) : null}
        </div>
      </div>
      {collapsed && elapsedMs !== null ? (
        <p className={styles.summary} data-testid="approve-steps-summary">
          <Icon name="check" size={16} />
          Done in {formatElapsed(elapsedMs)}: offer written, forecast updated, holdout set aside
        </p>
      ) : null}
    </div>
  );
}
