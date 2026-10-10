// The Desk's inbox as data: one row per gap, ranked by rupees at stake (pure, unit-tested in
// tests/e2e/feed-units.spec.ts). Several plays for one gap (the recorded one and any "Plan live"
// runs) collapse into the newest, with the rest listed as earlier runs.
import { plural } from "./plural";
import type { Gap, Play } from "./types";

export interface InboxGroup {
  gapId: string;
  /** The row's own play: the newest run for the gap. */
  newest: Play;
  /** Older runs for the same gap, newest first. */
  earlier: Play[];
}

/** Newest first: a run made in this session beats a stored one, then a later created_at, then
 * whichever came later in the list (the API lists oldest first, and a new run is appended). */
function newestFirst(plays: readonly Play[], liveIds: ReadonlySet<string>): Play[] {
  return plays
    .map((play, index) => ({ play, index }))
    .sort((a, b) => {
      const live = Number(liveIds.has(b.play.play_id)) - Number(liveIds.has(a.play.play_id));
      if (live !== 0) return live;
      const t = Date.parse(b.play.created_at || "") - Date.parse(a.play.created_at || "");
      if (Number.isFinite(t) && t !== 0) return t;
      return b.index - a.index;
    })
    .map((x) => x.play);
}

export function collapseRuns(
  plays: readonly Play[],
  gapsById: Readonly<Record<string, Pick<Gap, "rupees_at_stake"> | undefined>>,
  liveIds: ReadonlySet<string> = new Set(),
): InboxGroup[] {
  const byGap = new Map<string, Play[]>();
  for (const p of plays) {
    const list = byGap.get(p.gap_id);
    if (list) list.push(p);
    else byGap.set(p.gap_id, [p]);
  }
  const groups: InboxGroup[] = [];
  for (const [gapId, list] of byGap) {
    const [newest, ...earlier] = newestFirst(list, liveIds);
    groups.push({ gapId, newest, earlier });
  }
  // Array.prototype.sort is stable: equal rupees keep first-seen order.
  return groups.sort((a, b) => (gapsById[b.gapId]?.rupees_at_stake ?? 0) - (gapsById[a.gapId]?.rupees_at_stake ?? 0));
}

/** "Top 7 of 555 gaps by rupees at stake"; without a total, "Top 7 gaps by rupees at stake". */
export function inboxHeading(shown: number, totalGaps: number | null | undefined): string {
  const total = typeof totalGaps === "number" && totalGaps >= shown && totalGaps > 0 ? totalGaps : null;
  return total === null
    ? `Top ${shown} ${plural(shown, "gap")} by rupees at stake`
    : `Top ${shown} of ${total.toLocaleString("en-IN")} gaps by rupees at stake`;
}

export function earlierRunsLabel(n: number): string {
  return `+${n} earlier ${plural(n, "run")}`;
}
