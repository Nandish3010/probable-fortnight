import { test, expect } from "@playwright/test";
import {
  EMPTY_CRUMBS,
  NO_FACTS,
  clearCrumbs,
  crumbKey,
  deriveProgress,
  parseCrumbs,
  positionText,
  readCrumbs,
  serializeCrumbs,
  stepAccessibleName,
  stepById,
  stepForPath,
  stepViews,
  withApproved,
  writeCrumbs,
  STEPS,
  type ApiFacts,
  type Crumbs,
  type CrumbStorage,
} from "../../lib/progress";

// The pure rules behind the stepper (lib/progress.ts). The browser behaviour is in stepper.spec.ts.

const HERO = "gap_hero";

const play = (play_id: string, gap_id: string, status = "proposed") => ({ play_id, gap_id, status });
const facts = (over: Partial<ApiFacts>): ApiFacts => ({ ...NO_FACTS, ...over });
const crumbs = (over: Partial<Crumbs>): Crumbs => ({ ...EMPTY_CRUMBS, ...over });
const approvedCrumb = { play_id: "p1", gap_id: HERO, at: "2026-09-12T03:30:00Z" };

function fakeStorage(): CrumbStorage & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

test.describe("steps and routes", () => {
  test("five steps in order, each with its route and persona", () => {
    expect(STEPS.map((s) => [s.label, s.href, s.persona])).toEqual([
      ["Spot", "/phone", "Priya"],
      ["Plan", "/desk", "Arjun"],
      ["Approve", "/", "Arjun"],
      ["Offer", "/chat", "Meena"],
      ["Measure", "/outcomes", "Arjun"],
    ]);
  });

  test("a route belongs to one step; routes off the path to none", () => {
    expect(stepForPath("/")).toBe("approve");
    expect(stepForPath("/desk")).toBe("plan");
    expect(stepForPath("/desk/")).toBe("plan");
    expect(stepForPath("/phone")).toBe("spot");
    expect(stepForPath("/chat")).toBe("offer");
    expect(stepForPath("/outcomes")).toBe("measure");
    expect(stepForPath("/feedback")).toBeNull();
    expect(stepForPath("/dev/play-card")).toBeNull();
    expect(stepForPath(null)).toBeNull();
  });
});

test.describe("crumbs", () => {
  test("are namespaced by visitor id", () => {
    expect(crumbKey("abc")).not.toBe(crumbKey("def"));
    const s = fakeStorage();
    writeCrumbs(s, "abc", crumbs({ spot: true }));
    expect(readCrumbs(s, "abc").spot).toBe(true);
    expect(readCrumbs(s, "def").spot).toBe(false);
  });

  test("round-trip, and clearing forgets them", () => {
    const s = fakeStorage();
    const c = withApproved(crumbs({ spot: true, offer: true }), approvedCrumb);
    writeCrumbs(s, "v", c);
    expect(readCrumbs(s, "v")).toEqual(c);
    clearCrumbs(s, "v");
    expect(readCrumbs(s, "v")).toEqual(EMPTY_CRUMBS);
    expect(s.data.size).toBe(0);
  });

  test("an approval is recorded once per play", () => {
    const once = withApproved(EMPTY_CRUMBS, approvedCrumb);
    expect(withApproved(once, approvedCrumb).approved).toHaveLength(1);
    expect(withApproved(once, { ...approvedCrumb, play_id: "p2" }).approved).toHaveLength(2);
  });

  test("garbage in storage reads as no progress, never as an error", () => {
    expect(parseCrumbs(null)).toEqual(EMPTY_CRUMBS);
    expect(parseCrumbs("")).toEqual(EMPTY_CRUMBS);
    expect(parseCrumbs("not json")).toEqual(EMPTY_CRUMBS);
    expect(parseCrumbs("42")).toEqual(EMPTY_CRUMBS);
    expect(parseCrumbs('{"spot":"yes","approved":"nope"}')).toEqual(EMPTY_CRUMBS);
    expect(parseCrumbs(serializeCrumbs(crumbs({ plan: true }))).plan).toBe(true);
    // a malformed approval entry is dropped, a good one kept
    const mixed = parseCrumbs(JSON.stringify({ approved: [{ play_id: 1 }, approvedCrumb] }));
    expect(mixed.approved).toEqual([approvedCrumb]);
  });

  test("storage that throws (private window) reads as no progress", () => {
    const broken: CrumbStorage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readCrumbs(broken, "v")).toEqual(EMPTY_CRUMBS);
    expect(() => writeCrumbs(broken, "v", EMPTY_CRUMBS)).not.toThrow();
    expect(() => clearCrumbs(broken, "v")).not.toThrow();
    expect(readCrumbs(null, "v")).toEqual(EMPTY_CRUMBS);
  });
});

test.describe("deriveProgress", () => {
  test("a fresh visitor has nothing done", () => {
    const p = deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: [play("p1", HERO)], outcomes: [] }));
    expect(p).toMatchObject({ spot: false, plan: false, approve: false, offer: false, measure: false, restarted: false });
  });

  test("Approve is done when /plays has an approved play for the hero gap", () => {
    const p = deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: [play("p1", HERO, "approved")] }));
    expect(p.approve).toBe(true);
    expect(p.plan).toBe(true); // an approved play implies a plan was made
  });

  test("an approved play on another gap does not tick Approve when the hero has a play", () => {
    const p = deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: [play("p1", HERO), play("p2", "gap_other", "approved")] }));
    expect(p.approve).toBe(false);
  });

  test("... but when the tenant has no play for the hero gap, any approved play is the approval", () => {
    const p = deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: [play("p2", "gap_other", "approved")] }));
    expect(p.approve).toBe(true);
  });

  test("while /plays has not answered, the crumb carries the Approve tick", () => {
    const p = deriveProgress(HERO, crumbs({ approved: [approvedCrumb] }), NO_FACTS);
    expect(p.approve).toBe(true);
    expect(p.restarted).toBe(false);
  });

  test("Spot comes from its crumb alone", () => {
    expect(deriveProgress(HERO, crumbs({ spot: true }), NO_FACTS).spot).toBe(true);
    expect(deriveProgress(HERO, EMPTY_CRUMBS, NO_FACTS).spot).toBe(false);
  });

  test("Offer needs its crumb and an approval", () => {
    const approved = facts({ plays: [play("p1", HERO, "approved")] });
    expect(deriveProgress(HERO, crumbs({ offer: true }), approved).offer).toBe(true);
    expect(deriveProgress(HERO, crumbs({ offer: true }), facts({ plays: [play("p1", HERO)] })).offer).toBe(false);
    expect(deriveProgress(HERO, EMPTY_CRUMBS, approved).offer).toBe(false);
  });

  test("Measure needs a measured row and an approval; an unavailable /outcomes is unknown, not done", () => {
    const approved = [play("p1", HERO, "approved")];
    expect(deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: approved, outcomes: [{ status: "measured" }] })).measure).toBe(true);
    expect(deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: approved, outcomes: [{ status: "unmeasured" }] })).measure).toBe(false);
    const unknown = deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: approved, outcomes: null }));
    expect(unknown).toMatchObject({ measure: false, measureUnknown: true });
    // a measured row from the pre-baked example does not count before the visitor approved
    expect(deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: [play("p1", HERO)], outcomes: [{ status: "measured" }] })).measure).toBe(false);
  });

  test("sandbox restarted: the crumb says approved, /plays says proposed", () => {
    const p = deriveProgress(HERO, crumbs({ plan: true, offer: true, approved: [approvedCrumb] }), facts({ plays: [play("p1", HERO)] }));
    expect(p.restarted).toBe(true);
    expect(p.approve).toBe(false);
    expect(p.plan).toBe(false);
    expect(p.offer).toBe(false);
  });

  test("sandbox restarted: /plays answered 404, or Approve did", () => {
    const c = crumbs({ approved: [approvedCrumb] });
    expect(deriveProgress(HERO, c, facts({ playsNotFound: true })).restarted).toBe(true);
    expect(deriveProgress(HERO, c, facts({ approveNotFound: true })).restarted).toBe(true);
  });

  test("a restart is detected for any approved play, not only the hero's", () => {
    const c = crumbs({ approved: [{ play_id: "p9", gap_id: "gap_other", at: "2026-09-12T03:30:00Z" }] });
    expect(deriveProgress(HERO, c, facts({ plays: [play("p1", HERO), play("p9", "gap_other")] })).restarted).toBe(true);
  });

  test("a play merely missing from the list, or already running or measured, is not a restart", () => {
    const c = crumbs({ approved: [approvedCrumb] });
    expect(deriveProgress(HERO, c, facts({ plays: [play("p_other", "gap_other")] })).restarted).toBe(false);
    expect(deriveProgress(HERO, c, facts({ plays: [play("p1", HERO, "measured")] })).restarted).toBe(false);
    expect(deriveProgress(HERO, c, facts({ plays: [play("p1", HERO, "running")] })).approve).toBe(true);
  });

  test("a 404 with no recorded approval is not a restart", () => {
    expect(deriveProgress(HERO, EMPTY_CRUMBS, facts({ playsNotFound: true })).restarted).toBe(false);
  });
});

test.describe("stepViews", () => {
  const base = deriveProgress(HERO, EMPTY_CRUMBS, facts({ plays: [play("p1", HERO)], outcomes: [] }));

  test("current, next and locked at the start of the demo", () => {
    const v = stepViews("approve", base);
    expect(v.map((s) => s.state)).toEqual(["next", "next", "current", "locked", "locked"]);
    expect(v[3].hint).toBe("Approve a plan first");
    expect(v[3].shortHint).toBe("Approve first");
  });

  test("done steps, with the current one still marked current", () => {
    const p = deriveProgress(
      HERO,
      crumbs({ spot: true, offer: true }),
      facts({ plays: [play("p1", HERO, "approved")], outcomes: [{ status: "measured" }] }),
    );
    const v = stepViews("offer", p);
    expect(v.map((s) => s.state)).toEqual(["done", "done", "done", "current", "done"]);
    expect(v[3].done).toBe(true);
  });

  test("the current step is never locked, even before its prerequisite", () => {
    expect(stepViews("measure", base)[4].state).toBe("current");
    expect(stepViews("offer", base)[3].state).toBe("current");
  });

  test("restarted: everything except Spot is locked, and says to start again", () => {
    const p = deriveProgress(HERO, crumbs({ spot: true, approved: [approvedCrumb] }), facts({ plays: [play("p1", HERO)] }));
    const v = stepViews("approve", p);
    expect(v.map((s) => s.state)).toEqual(["done", "locked", "current", "locked", "locked"]);
    expect(v[1].shortHint).toBe("Start again");
  });

  test("a route off the path has no current step and still returns five views", () => {
    expect(stepViews(null, base).map((s) => s.state)).toEqual(["next", "next", "next", "locked", "locked"]);
  });
});

test.describe("labels", () => {
  test("position text", () => {
    expect(positionText("approve")).toBe("Step 3 of 5: Approve");
    expect(positionText("spot")).toBe("Step 1 of 5: Spot");
    expect(positionText(null)).toBe("Taal demo");
  });

  test("accessible names keep the old destination names discoverable", () => {
    const base = deriveProgress(HERO, EMPTY_CRUMBS, NO_FACTS);
    const views = stepViews("approve", base);
    const names = STEPS.map((s, i) => stepAccessibleName(s, views[i]));
    expect(names[0]).toBe("Spot: Phone view (Priya)");
    expect(names[1]).toBe("Plan: Play Desk (Arjun)");
    expect(names[3]).toBe("Offer: Chat (Meena), approve a plan first");
    expect(names[4]).toBe("Measure: Outcomes (Arjun), approve a plan first");
    const done = stepViews("approve", { ...base, spot: true });
    expect(stepAccessibleName(stepById("spot"), done[0])).toBe("Spot: Phone view (Priya), done");
  });
});
