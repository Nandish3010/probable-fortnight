"use client";

import { Details } from "./Details";
import { Icon } from "./icons";
import { SourceBadge } from "./SourceBadge";
import { formatDate, inr, relativeDate } from "../lib/format";
import { earlierRunsLabel, type InboxGroup } from "../lib/inbox";
import { label, labelList } from "../lib/labels";
import type { Gap } from "../lib/types";
import styles from "./InboxRow.module.css";

/** A deadline within this many days (or already past) is shown as urgent. */
const URGENT_DAYS = 3;

const STATUS_TEXT: Record<string, string> = {
  proposed: "Proposed",
  approved: "Approved",
  modified: "Modified",
  rejected: "Rejected",
  running: "Running",
  measured: "Measured",
  unmeasured: "Unmeasured",
};

/** One gap in the Desk's inbox: the product, where, whether it is decided (status chip), when it
 * is due (relative chip, full date on hover) and the rupees at stake. Several runs for one gap
 * are one row; the older ones are listed under "+N earlier runs" and can be opened from there. */
export function InboxRow({
  group,
  gap,
  now,
  selectedId,
  liveIds,
  onSelect,
}: {
  group: InboxGroup;
  gap?: Gap;
  now?: Date;
  selectedId: string | null;
  liveIds: ReadonlySet<string>;
  onSelect: (playId: string) => void;
}) {
  const p = group.newest;
  const all = [p, ...group.earlier];
  const selectedHere = all.some((x) => x.play_id === selectedId);
  // Relative to the demo clock the server reports; until it has loaded, the plain date.
  const dueDate = gap?.deadline_date ?? p.target.deadline_date;
  const due = now ? relativeDate(dueDate, now) : null;
  const dueText = due?.text ?? (dueDate ? formatDate(dueDate) : null);
  const urgent = due !== null && due.days <= URGENT_DAYS;
  const approved = p.status === "approved";

  return (
    <div className={styles.row} data-testid="inbox-row" data-gap={group.gapId}>
      <button
        type="button"
        className={`inbox__item ${selectedHere ? "inbox__item--active" : ""}`}
        aria-current={p.play_id === selectedId ? "true" : undefined}
        onClick={() => onSelect(p.play_id)}
      >
        <span className={styles.top}>
          <strong>{gap?.evidence.sku_name ?? label("sku", p.target.sku)}</strong>
          {liveIds.has(p.play_id) ? <span className="chip inbox__live">Live run</span> : null}
        </span>
        <span className={`muted ${styles.sub}`}>
          {labelList("node", p.target.node_ids)} · {label("mechanic", p.mechanic)}
        </span>
        <span className={styles.meta}>
          <span className={`${styles.chip} ${approved ? styles.chipDone : ""}`} data-testid="inbox-status">
            {approved ? <Icon name="check" size={12} /> : null}
            {STATUS_TEXT[p.status] ?? p.status}
          </span>
          {dueText ? (
            <span className={`${styles.chip} ${urgent ? styles.chipUrgent : ""}`} data-testid="inbox-due" title={due?.absolute}>
              <Icon name="clock" size={12} />
              {dueText}
            </span>
          ) : null}
          <span className={`num ${styles.stake}`}>{inr(gap?.rupees_at_stake ?? 0)} at stake</span>
        </span>
      </button>
      {group.earlier.length > 0 ? (
        <Details variant="card" testId="earlier-runs" summary={earlierRunsLabel(group.earlier.length)}>
          <ul className={styles.earlier}>
            {group.earlier.map((e) => (
              <li key={e.play_id}>
                <button
                  type="button"
                  className={styles.earlierButton}
                  aria-current={e.play_id === selectedId ? "true" : undefined}
                  onClick={() => onSelect(e.play_id)}
                >
                  {e.source ? <SourceBadge source={e.source} /> : null}
                  <span>{STATUS_TEXT[e.status] ?? e.status}</span>
                  <span className={`id ${styles.runId}`}>{e.play_id}</span>
                </button>
              </li>
            ))}
          </ul>
        </Details>
      ) : null}
    </div>
  );
}
