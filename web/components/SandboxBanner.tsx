"use client";

import { Icon } from "./icons";
import { clearProgress, useProgress } from "../lib/progressStore";
import styles from "./SandboxBanner.module.css";

/** Shown when this browser remembers an approval that the demo server no longer knows: the server
 * was restarted (it keeps sandboxes in memory), so the visitor's progress is gone. One banner, one
 * way out: "Start again" forgets the local progress so the stepper and the cards begin from step
 * one. It does not touch the server. */
export function SandboxBanner() {
  const { progress } = useProgress();
  if (!progress.restarted) return null;
  return (
    <div className={styles.wrap}>
      <div className={styles.banner} role="status" data-testid="sandbox-banner">
        <span className={styles.icon} aria-hidden="true">
          <Icon name="alert-triangle" size={20} />
        </span>
        <p className={styles.text}>Your demo session was restarted. Run the demo again from the start.</p>
        <button
          type="button"
          className={styles.button}
          onClick={() => {
            clearProgress();
            // The banner goes away with this button: keep keyboard focus on the page.
            document.getElementById("main-content")?.focus({ preventScroll: true });
          }}
        >
          Start again
        </button>
      </div>
    </div>
  );
}
