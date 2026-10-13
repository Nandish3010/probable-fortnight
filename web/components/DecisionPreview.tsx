import type { ReactNode } from "react";
import { playImpact } from "../lib/impact";
import { GAP_TYPE_LABEL, label } from "../lib/labels";
import { whyNow, whyNowInput } from "../lib/playText";
import type { Gap, Play } from "../lib/types";
import { RecoveredFigure } from "./RecoveredFigure";
import styles from "./DecisionPreview.module.css";

/** The decision card before "Run the 60-second beat" is pressed: what is at stake, the projected
 * figure, and the one primary button. It reads the same prefetched gap and play the opened card
 * will show, so the click only reveals the rest (the comparison bars, the checks, Approve). Until
 * those arrive it says what the click does. It carries none of the opened card's test ids. */
export function DecisionPreview({
  gap,
  play,
  now,
  children,
}: {
  gap: Gap | null;
  play: Play | null;
  now?: Date;
  /** The button (and what sits beside it). */
  children: ReactNode;
}) {
  const ready = gap && play;
  const impact = ready ? playImpact(play, { rupees_at_stake: gap.rupees_at_stake }) : null;
  const skuName = ready ? (gap.evidence.sku_name ?? label("sku", play.target.sku)) : null;
  const sub = ready ? `${label("node", gap.node_id)} · ${GAP_TYPE_LABEL[gap.type] ?? gap.type}` : null;
  const why = ready ? whyNow(whyNowInput(play, gap), now) : null;

  return (
    <div className={styles.preview} data-testid="decision-preview">
      <p className={styles.eyebrow}>Top decision today{sub ? ` · ${sub}` : ""}</p>
      <h2 className={styles.title}>{skuName ?? "One stock gap, one proposed play"}</h2>
      {why && impact ? (
        <>
          <p className={styles.why}>{why.text}</p>
          <RecoveredFigure impact={impact} testId="preview-figure" countOnce />
          <p className={styles.honesty}>A projection, not a measurement.</p>
        </>
      ) : (
        <p className={styles.note}>One click opens a real stock gap and its pre-proposed play, and stops at Approve.</p>
      )}
      <div className={styles.actions}>{children}</div>
    </div>
  );
}
