import { Badge, BADGE_HELP, type BadgeKind } from "./Badge";
import styles from "./StateLegend.module.css";

const KINDS: BadgeKind[] = ["live", "replay", "synthetic"];

/** One compact element that says what LIVE, REPLAY and SYNTHETIC mean. Each badge in the summary
 * carries its own tooltip (the same sentence the badge has everywhere, from BADGE_HELP); opening
 * the element prints the three sentences, because a tooltip alone does not exist on a phone. */
export function StateLegend() {
  return (
    <details className={styles.legend} data-testid="state-legend">
      <summary className={styles.summary}>
        <span>What do</span>
        {KINDS.map((k) => (
          <Badge key={k} kind={k} />
        ))}
        <span>mean?</span>
      </summary>
      <dl className={styles.list}>
        {KINDS.map((k) => (
          <div key={k} className={styles.row}>
            <dt>
              <Badge kind={k} title={BADGE_HELP[k]} />
            </dt>
            <dd>{BADGE_HELP[k]}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
