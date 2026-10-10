import { test, expect } from "@playwright/test";
import { pickFeed } from "../../lib/feed";
import { collapseRuns, earlierRunsLabel, inboxHeading } from "../../lib/inbox";
import type { Gap, Play } from "../../lib/types";

// The pure parts of the phone feed and the Desk inbox (lib/feed.ts, lib/inbox.ts). The browser
// behaviour is in feed-phone.spec.ts and desk-phone.spec.ts.

const gap = (gap_id: string, rupees_at_stake: number): Gap => ({ gap_id, rupees_at_stake }) as Gap;
const play = (play_id: string, gap_id: string, created_at = "2026-09-12T03:30:00Z"): Play => ({ play_id, gap_id, created_at }) as Play;

test.describe("pickFeed", () => {
  const gaps = [gap("g_small", 100), gap("g_hero", 500), gap("g_big", 9000), gap("g_mid", 3000), gap("g_noplan", 8000)];
  const plays = [play("p_small", "g_small"), play("p_hero", "g_hero"), play("p_big", "g_big"), play("p_mid", "g_mid")];

  test("the hero gap first, then the next biggest gaps that have a plan", () => {
    const feed = pickFeed(gaps, plays, "g_hero");
    expect(feed.map((i) => i.gap.gap_id)).toEqual(["g_hero", "g_big", "g_mid"]);
    expect(feed.map((i) => i.play?.play_id)).toEqual(["p_hero", "p_big", "p_mid"]);
  });

  test("a gap with no plan is skipped after the hero (nothing to decide)", () => {
    expect(pickFeed(gaps, plays, "g_hero").some((i) => i.gap.gap_id === "g_noplan")).toBe(false);
  });

  test("a hero gap with no plan still leads, as the gap alone", () => {
    const feed = pickFeed(gaps, plays.filter((p) => p.gap_id !== "g_hero"), "g_hero");
    expect(feed[0]).toMatchObject({ play: null });
    expect(feed[0].gap.gap_id).toBe("g_hero");
    expect(feed).toHaveLength(3);
  });

  test("without the hero gap the biggest gap leads", () => {
    expect(pickFeed(gaps, plays, "g_missing")[0].gap.gap_id).toBe("g_big");
  });

  test("fewer decisions than the size is fine, and nothing is nothing", () => {
    expect(pickFeed([gap("g_hero", 5)], [play("p_hero", "g_hero")], "g_hero")).toHaveLength(1);
    expect(pickFeed([], plays, "g_hero")).toEqual([]);
  });

  test("several runs of one gap show as one card: the newest", () => {
    const runs = [play("p_old", "g_hero", "2026-09-12T03:30:00Z"), play("p_new", "g_hero", "2026-09-13T03:30:00Z")];
    const feed = pickFeed([gap("g_hero", 5)], runs, "g_hero");
    expect(feed).toHaveLength(1);
    expect(feed[0].play?.play_id).toBe("p_new");
  });
});

test.describe("collapseRuns", () => {
  const gapsById = { g1: gap("g1", 100), g2: gap("g2", 900) };

  test("one row per gap, ranked by rupees at stake", () => {
    const groups = collapseRuns([play("a", "g1"), play("b", "g2")], gapsById);
    expect(groups.map((g) => g.gapId)).toEqual(["g2", "g1"]);
  });

  test("the newest run is the row, the rest are earlier runs, newest first", () => {
    const groups = collapseRuns(
      [play("a", "g1", "2026-09-01T00:00:00Z"), play("c", "g1", "2026-09-03T00:00:00Z"), play("b", "g1", "2026-09-02T00:00:00Z")],
      gapsById,
    );
    expect(groups).toHaveLength(1);
    expect(groups[0].newest.play_id).toBe("c");
    expect(groups[0].earlier.map((p) => p.play_id)).toEqual(["b", "a"]);
  });

  test("a run made in this session beats a stored one with the same timestamp; list order breaks other ties", () => {
    const same = "2026-09-12T03:30:00Z";
    const live = collapseRuns([play("live_run", "g1", same), play("stored_run", "g1", same)], gapsById, new Set(["live_run"]));
    expect(live[0].newest.play_id).toBe("live_run"); // the stored one is later in the list, but the live one wins
    const tie = collapseRuns([play("first", "g1", same), play("second", "g1", same)], gapsById);
    expect(tie[0].newest.play_id).toBe("second");
  });

  test("a gap the API does not list ranks last", () => {
    const groups = collapseRuns([play("x", "g_unknown"), play("a", "g1")], gapsById);
    expect(groups.map((g) => g.gapId)).toEqual(["g1", "g_unknown"]);
  });
});

test.describe("inbox copy", () => {
  test("the heading names the portfolio total when it is known", () => {
    expect(inboxHeading(7, 555)).toBe("Top 7 of 555 gaps by rupees at stake");
    expect(inboxHeading(7, 1234)).toBe("Top 7 of 1,234 gaps by rupees at stake");
  });

  test("... and omits it when it is not", () => {
    expect(inboxHeading(7, null)).toBe("Top 7 gaps by rupees at stake");
    expect(inboxHeading(7, undefined)).toBe("Top 7 gaps by rupees at stake");
    expect(inboxHeading(7, 3)).toBe("Top 7 gaps by rupees at stake"); // a total below the count is not a total
    expect(inboxHeading(1, null)).toBe("Top 1 gap by rupees at stake");
  });

  test("earlier runs", () => {
    expect(earlierRunsLabel(1)).toBe("+1 earlier run");
    expect(earlierRunsLabel(2)).toBe("+2 earlier runs");
  });
});
