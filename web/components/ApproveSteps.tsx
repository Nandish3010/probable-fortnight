"use client";

import { APPROVE_STEPS, copyStepLine, workingCopy } from "../lib/approveMachine";
import { PROVENANCE } from "../lib/planSteps";
import { Icon } from "./icons";
import styles from "./ApproveSteps.module.css";

/** What produced each Approve step. While the request is in flight the copy step makes no claim about
 * its source (it is not known yet). Once the response arrives the line comes from copyStepLine(), the same
 * mapping as the badge on the result (copySourceLabel), so the two cannot disagree; a response that names
 * no known source gets no line at all. */
function provenance(i: number, waiting: boolean, copy: CopyInfo): string | null {
  if (i === 0) return waiting ? PROVENANCE.offerCopyPending : copyStepLine(copy);
  return PROVENANCE.deterministic;
}

type CopyInfo = { source?: unknown; provenance?: unknown } | null | undefined;

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
  copy = null,
}: {
  /** 0 while waiting; 1 to 3 as the response's ticks land. */
  ticked: number;
  collapsed: boolean;
  /** Whole seconds waited so far (from performance.now(), not an interval counter). */
  seconds: number;
  /** Click to response, once known. */
  elapsedMs: number | null;
  /** `copy` of the response (source, provenance), when it has one. */
  copy?: CopyInfo;
}) {
  const waiting = elapsedMs === null;
  return (
    <div className={styles.steps} data-testid="approve-steps" data-collapsed={collapsed ? "true" : "false"}>
      <div className={`${styles.fold} ${collapsed ? styles.folded : ""}`} inert={collapsed ? true : undefined}>
        <div className={styles.foldInner}>
          <ol className={styles.list}>
            {APPROVE_STEPS.map((label, i) => {
              const done = i < ticked;
              const line = provenance(i, waiting, copy);
              return (
                <li key={label} className={styles.item} data-state={done ? "done" : "working"} data-testid="approve-step">
                  <span className={`${styles.mark} ${done ? styles.markDone : ""}`} aria-hidden="true">
                    {done ? <Icon name="check" size={14} /> : <span className={styles.dot} />}
                  </span>
                  <span className={styles.label}>
                    {label}
                    {line ? (
                      <span className={styles.prov} data-testid="step-provenance">
                        {line}
                      </span>
                    ) : null}
                  </span>
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
          {/* No per-run time here: Approve's duration is a measured range stated in the README, not a number this page makes up. */}
          Done: offer written, forecast updated, holdout set aside
        </p>
      ) : null}
    </div>
  );
}
