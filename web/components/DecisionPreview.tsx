import type { ReactNode } from "react";
import { GAP_TYPE_LABEL, label } from "../lib/labels";
import type { Gap, Play } from "../lib/types";
import styles from "./DecisionPreview.module.css";

/** The decision card before "Run the 60-second beat" is pressed: which gap, what the click does, and the one
 * primary button. The projected figure and the user line are the hero's own (components/HeroProof.tsx, the
 * line under the hero sentence), so this card does not say them a second time. It reads the same prefetched
 * gap and play the opened card will show, so the click only reveals the rest (the comparison bars, the
 * checks, Approve). It carries none of the opened card's test ids. */
export function DecisionPreview({
  gap,
  play,
  children,
}: {
  gap: Gap | null;
  play: Play | null;
  /** The button (and what sits beside it). */
  children: ReactNode;
}) {
  const ready = gap && play;
  const skuName = ready ? (gap.evidence.sku_name ?? label("sku", play.target.sku)) : null;
  const sub = ready ? `${label("node", gap.node_id)} · ${GAP_TYPE_LABEL[gap.type] ?? gap.type}` : null;

  return (
    <div className={styles.preview} data-testid="decision-preview">
      <p className={styles.eyebrow}>Top decision today{sub ? ` · ${sub}` : ""}</p>
      <h2 className={styles.title}>{skuName ?? "One stock gap, one proposed play"}</h2>
      <p className={styles.note}>One click opens a real stock gap and its pre-proposed play, and stops at Approve.</p>
      <div className={styles.actions}>{children}</div>
    </div>
  );
}
