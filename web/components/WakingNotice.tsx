"use client";

import { useEffect, useRef } from "react";
import type { WakingPhase } from "../lib/useWaking";
import styles from "./WakingNotice.module.css";

export const WAKING_TEXT = "Waking the demo. It sleeps when idle, so the first load can take a little longer. Nothing is wrong.";
export const SLOW_TEXT = "The demo is slow to wake. Try again";

/** A calm inline notice for a first load that is taking a while (lib/useWaking.ts): not a modal, not
 * a toast. The wrapper is a polite live region that is always in the DOM and empty until the notice
 * has something to say, so a screen reader announces it when it appears. The "waking" phase shows no
 * motion at all under prefers-reduced-motion; the "slow" phase offers Retry (the page's own load).
 *
 * Place it BELOW the content it stands in for, never above a button the visitor is about to press, so
 * its arrival and removal move nothing the visitor is aiming at. */
export function WakingNotice({ phase, onRetry, className = "" }: { phase: WakingPhase; onRetry?: () => void; className?: string }) {
  // Retry removes the notice when it works, taking keyboard focus with it: hand focus to <main> then.
  const hadFocus = useRef(false);
  useEffect(
    () => () => {
      if (hadFocus.current && (document.activeElement === document.body || document.activeElement === null)) {
        document.getElementById("main-content")?.focus({ preventScroll: true });
      }
    },
    [],
  );
  return (
    <div role="status" aria-live="polite" className={`${styles.region} ${className}`}>
      {phase === "idle" ? null : (
        <div
          className={styles.notice}
          data-testid="waking-notice"
          data-phase={phase}
          onFocusCapture={() => {
            hadFocus.current = true;
          }}
          onBlurCapture={(e) => {
            if (e.relatedTarget && !e.currentTarget.contains(e.relatedTarget as Node)) hadFocus.current = false;
          }}
        >
          <span className={styles.dot} data-phase={phase} aria-hidden="true" />
          <p className={styles.text}>{phase === "waking" ? WAKING_TEXT : SLOW_TEXT}</p>
          {phase === "slow" && onRetry ? (
            <button type="button" className={styles.retry} onClick={onRetry} data-testid="waking-retry">
              Retry
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
