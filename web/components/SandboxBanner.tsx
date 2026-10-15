"use client";

import { Icon } from "./icons";
import { useRestartNote } from "../lib/sessionNote";
import styles from "./SandboxBanner.module.css";

export const RESTART_NOTE_TEXT = "Your demo session was restarted, so we began a new one for you.";

/** A returning visitor's browser remembered progress that the demo server no longer has (it keeps sandboxes
 * in memory and restarts). The app has already started a new session by itself (lib/session.ts,
 * lib/progressStore.ts), so this is only a word of explanation: one calm line that goes by itself, with no
 * button, because nothing is waiting on the visitor. It floats under the nav, so it moves nothing on the
 * page, and it is not shown while a "Waking the demo" notice is (lib/sessionNote.ts). */
export function SandboxBanner() {
  const show = useRestartNote();
  if (!show) return null;
  return (
    <div className={styles.wrap}>
      <div className={styles.banner} role="status" data-testid="sandbox-banner">
        <span className={styles.icon} aria-hidden="true">
          <Icon name="info" size={20} />
        </span>
        <p className={styles.text}>{RESTART_NOTE_TEXT}</p>
      </div>
    </div>
  );
}
