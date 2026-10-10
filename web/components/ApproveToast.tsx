"use client";

import { useCallback, useEffect, useRef } from "react";
import { Icon } from "./icons";
import styles from "./ApproveToast.module.css";

export const TOAST_MS = 5000;

/**
 * The one toast after Approve (design_spec.md 6.3): five seconds, paused while the pointer or
 * keyboard focus is on it, with a real dismiss button. It carries no live-region role on purpose:
 * the panel's own persistent region announces the result, and a second announcement would read it twice.
 */
export function ApproveToast({ message, onDone }: { message: string; onDone: () => void }) {
  const remaining = useRef(TOAST_MS);
  const startedAt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hovered = useRef(false);
  const focused = useRef(false);
  const done = useRef(onDone);
  done.current = onDone;

  const start = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    startedAt.current = performance.now();
    timer.current = setTimeout(() => done.current(), remaining.current);
  }, []);

  const pause = useCallback(() => {
    if (!timer.current) return;
    clearTimeout(timer.current);
    timer.current = null;
    remaining.current = Math.max(0, remaining.current - (performance.now() - startedAt.current));
  }, []);

  useEffect(() => {
    start();
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [start]);

  const resumeIfIdle = () => {
    if (!hovered.current && !focused.current) start();
  };

  return (
    <div
      className={styles.toast}
      data-testid="approve-toast"
      onMouseEnter={() => {
        hovered.current = true;
        pause();
      }}
      onMouseLeave={() => {
        hovered.current = false;
        resumeIfIdle();
      }}
      onFocus={() => {
        focused.current = true;
        pause();
      }}
      onBlur={() => {
        focused.current = false;
        resumeIfIdle();
      }}
    >
      <span className={styles.icon} aria-hidden="true">
        <Icon name="check" size={16} />
      </span>
      <p className={styles.text}>{message}</p>
      <button type="button" className={styles.dismiss} onClick={onDone} aria-label="Dismiss">
        <Icon name="x" size={16} />
      </button>
    </div>
  );
}
