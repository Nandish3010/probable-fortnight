// Which decisions the phone feed shows (pure, unit-tested in tests/e2e/feed-units.spec.ts): the
// hero gap first, then the next biggest gaps by rupees at stake that have a plan to decide on.
import { collapseRuns } from "./inbox";
import type { Gap, Play } from "./types";

export interface FeedItem {
  gap: Gap;
  /** Null only for the hero gap when it has no plan; the card then degrades to the gap alone. */
  play: Play | null;
}

export const FEED_SIZE = 3;

export function pickFeed(gaps: readonly Gap[], plays: readonly Play[], heroGapId: string, size = FEED_SIZE): FeedItem[] {
  if (gaps.length === 0 || size <= 0) return [];
  const gapsById: Record<string, Gap> = {};
  for (const g of gaps) gapsById[g.gap_id] = g;
  // One play per gap: the newest.
  const playByGap = new Map(collapseRuns(plays, gapsById).map((g) => [g.gapId, g.newest] as const));

  const ranked = [...gaps].sort((a, b) => b.rupees_at_stake - a.rupees_at_stake);
  const hero = ranked.find((g) => g.gap_id === heroGapId) ?? ranked[0];
  const items: FeedItem[] = [{ gap: hero, play: playByGap.get(hero.gap_id) ?? null }];
  for (const g of ranked) {
    if (items.length >= size) break;
    if (g.gap_id === hero.gap_id) continue;
    const play = playByGap.get(g.gap_id);
    if (play) items.push({ gap: g, play });
  }
  return items;
}
