"use client";

import { useEffect, useRef, useState } from "react";
import { toApiError, type ApiError } from "../lib/apiError";
import { DEFAULT_RETRY_SECONDS, errorCopy } from "../lib/errorCopy";
import styles from "./ErrorCard.module.css";

/** Whole seconds left before a model_unavailable retry is allowed; ticks once a second. */
function useCountdown(seconds: number, active: boolean): number {
  const [left, setLeft] = useState(active ? seconds : 0);
  useEffect(() => {
    if (!active) return;
    setLeft(seconds);
    const started = Date.now();
    const id = setInterval(() => {
      const remaining = Math.max(0, seconds - Math.floor((Date.now() - started) / 1000));
      setLeft(remaining);
      if (remaining === 0) clearInterval(id);
    }, 250);
    return () => clearInterval(id);
  }, [seconds, active]);
  return left;
}

/**
 * Every failed load, call and stream renders through this card instead of a spinner that never
 * ends. role="alert" so a screen reader hears it at once. For model_unavailable the Retry button
 * waits out the number of seconds the server asked for (a retry sooner only meets the same 503).
 */
export function ErrorCard({
  error,
  onRetry,
  onShowRecorded,
  compact = false,
  title,
  body,
}: {
  error: ApiError | Error | unknown;
  onRetry?: () => void;
  /** Offered only where a recorded copy of the data exists on the client. */
  onShowRecorded?: () => void;
  compact?: boolean;
  /** Overrides for the rare place the generic copy would be wrong (e.g. a re-plan 409). */
  title?: string;
  body?: string;
}) {
  const err = toApiError(error);
  const copy = errorCopy(err);
  const waits = err.kind === "model_unavailable" && Boolean(onRetry);
  const wait = err.retryAfterSeconds ?? DEFAULT_RETRY_SECONDS;
  const left = useCountdown(wait, waits);
  const locked = waits && left > 0;

  // Retry removes this card when it works, taking keyboard focus with it. When that happens,
  // hand focus to the page's main region instead of dropping it on <body>.
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
    <div
      className={`${styles.card} ${compact ? styles.compact : ""}`}
      role="alert"
      onFocusCapture={() => {
        hadFocus.current = true;
      }}
      onBlurCapture={(e) => {
        if (e.relatedTarget && !e.currentTarget.contains(e.relatedTarget as Node)) hadFocus.current = false;
      }}
      data-testid="error-card"
      data-error-kind={err.kind}
    >
      <p className={styles.title}>{title ?? copy.title}</p>
      <p className={styles.body}>{body ?? copy.body}</p>
      {onRetry || onShowRecorded ? (
        <div className={styles.actions}>
          {onRetry ? (
            <button type="button" className={styles.retry} onClick={onRetry} disabled={locked} data-testid="error-retry">
              {locked ? `Retry in ${left} s` : "Retry"}
            </button>
          ) : null}
          {onShowRecorded ? (
            <button type="button" className={styles.recorded} onClick={onShowRecorded} data-testid="error-show-recorded">
              Show recorded result
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
