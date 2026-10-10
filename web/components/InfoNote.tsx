"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Icon } from "./icons";
import styles from "./InfoNote.module.css";

/** A small "i" button that opens a note in place (not a floating popover, so it is never clipped
 * and never covers what it explains). Esc closes it and returns focus to the button. */
export function InfoNote({
  label,
  children,
  lead,
  testId,
}: {
  label: string;
  children: ReactNode;
  /** Content that shares the button's row (a legend); the note opens full width beneath the row. */
  lead?: ReactNode;
  testId?: string;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className={styles.root} data-testid={testId}>
      <div className={styles.row}>
        {lead}
        <button
          ref={buttonRef}
          type="button"
          className={styles.button}
          aria-expanded={open}
          aria-controls={open ? id : undefined}
          aria-label={label}
          onClick={() => setOpen((o) => !o)}
          data-testid={testId ? `${testId}-button` : undefined}
        >
          <Icon name="info" size={16} />
        </button>
      </div>
      {open ? (
        <p id={id} className={styles.note} data-testid={testId ? `${testId}-note` : undefined}>
          {children}
        </p>
      ) : null}
    </div>
  );
}
