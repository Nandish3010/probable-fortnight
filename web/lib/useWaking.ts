"use client";

import { useEffect, useState } from "react";

// "Waking the demo": the service runs with no warm instance when idle, so the first read after a
// quiet spell can take a long time and a pane would look empty. This says what is going on once a
// first load has been pending for a moment, and goes the moment data arrives.

/** How long a first load may be pending before the notice appears. */
export const WAKE_AFTER_MS = 1500;
/** How long before the notice stops reassuring and offers Retry. */
export const SLOW_AFTER_MS = 45_000;

export type WakingPhase = "idle" | "waking" | "slow";

/** The phase for a load that has been pending `elapsedMs` (null when nothing is pending). A failed
 * load is "slow" at once: whatever the cause, the useful thing to offer is a retry. Pure, so the
 * thresholds are unit-tested in node. */
export function wakingPhase(elapsedMs: number | null, failed = false): WakingPhase {
  if (failed) return "slow";
  if (elapsedMs === null) return "idle";
  if (elapsedMs >= SLOW_AFTER_MS) return "slow";
  if (elapsedMs >= WAKE_AFTER_MS) return "waking";
  return "idle";
}

/** Follows one load. `pending` is true while it is in flight; `failed` when it ended in an error the
 * page does not otherwise show; `epoch` is bumped when the load is started again (Retry), which
 * restarts the clock even though `pending` never went false in between. */
export function useWaking(pending: boolean, failed = false, epoch = 0): WakingPhase {
  const [elapsed, setElapsed] = useState<number | null>(null);
  useEffect(() => {
    if (!pending) {
      setElapsed(null);
      return;
    }
    setElapsed(0);
    const started = Date.now();
    const wake = setTimeout(() => setElapsed(Date.now() - started), WAKE_AFTER_MS);
    const slow = setTimeout(() => setElapsed(Date.now() - started), SLOW_AFTER_MS);
    return () => {
      clearTimeout(wake);
      clearTimeout(slow);
    };
  }, [pending, epoch]);
  return wakingPhase(pending ? elapsed : null, failed);
}
