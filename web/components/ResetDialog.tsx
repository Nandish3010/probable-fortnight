"use client";

import { useEffect, useRef } from "react";
import styles from "./ResetDialog.module.css";

/** "Reset demo data?" as a native modal <dialog>: the browser traps focus inside it, Escape cancels
 * it, and focus returns to the button that opened it. Nothing is cleared until Reset is pressed. */
export function ResetDialog({
  open,
  busy = false,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dlg = ref.current;
    if (!dlg) return;
    if (open && !dlg.open) dlg.showModal();
    if (!open && dlg.open) dlg.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className={styles.dialog}
      aria-labelledby="reset-dialog-title"
      onCancel={(e) => {
        // Escape: let the parent close it so its state stays the single source of truth.
        e.preventDefault();
        onCancel();
      }}
      onClose={() => {
        if (open) onCancel();
      }}
      data-testid="reset-dialog"
    >
      <h2 id="reset-dialog-title" className={styles.title}>
        Reset demo data?
      </h2>
      <p className={styles.body}>This clears your plans and chat for this session. It does not affect anyone else.</p>
      <div className={styles.actions}>
        <button type="button" className={styles.confirm} onClick={onConfirm} disabled={busy}>
          Reset
        </button>
        <button type="button" className={styles.cancel} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </dialog>
  );
}
