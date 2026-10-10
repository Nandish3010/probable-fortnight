// Where the visitor is in the five-step loop, derived and never stored on the server
// (ux_plan.md section 3, design_spec.md section 7). Pure functions only: no window, no fetch, so
// the rules are unit-tested in node (tests/e2e/progress-units.spec.ts). The browser side that reads
// localStorage and asks the API lives in lib/progressStore.ts.
//
// Where each tick comes from:
//   Spot     crumb, written by the phone view after Confirm rows succeeds
//   Plan     crumb, written when the Desk opens a play; also implied by an approved play
//   Approve  /plays has a play for the hero gap with status "approved" (crumbs bridge the gap
//            while /plays has not answered, and disagree with it after a sandbox restart)
//   Offer    crumb, written by the chat after a reply; only counts once Approve is done
//   Measure  /outcomes has a measured row for a play the visitor approved; only counts once Approve is done
// The crumbs live in localStorage under a key namespaced by the visitor id, so two visitors on one
// browser profile do not read each other's progress, and "Reset demo data" clears them.

export type StepId = "spot" | "plan" | "approve" | "offer" | "measure";

export const STEP_IDS: readonly StepId[] = ["spot", "plan", "approve", "offer", "measure"];

export interface StepDef {
  id: StepId;
  /** The verb on the stepper. */
  label: string;
  href: string;
  /** Who does this step in the story. Text only; no avatars in this phase. */
  persona: string;
  /** The screen the step opens. */
  destination: string;
}

export const STEPS: readonly StepDef[] = [
  { id: "spot", label: "Spot", href: "/phone", persona: "Priya", destination: "Phone view" },
  { id: "plan", label: "Plan", href: "/desk", persona: "Arjun", destination: "Play Desk" },
  { id: "approve", label: "Approve", href: "/", persona: "Arjun", destination: "Decision card" },
  { id: "offer", label: "Offer", href: "/chat", persona: "Meena", destination: "Chat" },
  { id: "measure", label: "Measure", href: "/outcomes", persona: "Arjun", destination: "Outcomes" },
];

export function stepById(id: StepId): StepDef {
  return STEPS.find((s) => s.id === id) as StepDef;
}

/** The step a route belongs to; null for a route outside the five-step path. */
export function stepForPath(pathname: string | null | undefined): StepId | null {
  if (!pathname) return null;
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return STEPS.find((s) => s.href === clean)?.id ?? null;
}

export type StepState = "done" | "current" | "next" | "locked";

// ---------- crumbs ----------

export interface ApprovedCrumb {
  play_id: string;
  gap_id: string;
  /** ISO time the visitor approved it. */
  at: string;
}

export interface Crumbs {
  spot: boolean;
  plan: boolean;
  offer: boolean;
  approved: ApprovedCrumb[];
  /** Plays whose "fast-forward one day" sequence (E2) has already run in this session. Written by
   * the Outcomes page and cleared by Reset with the rest of the crumbs; it makes the button
   * single-use. */
  fastForwarded: string[];
}

export const EMPTY_CRUMBS: Crumbs = { spot: false, plan: false, offer: false, approved: [], fastForwarded: [] };

export const CRUMB_KEY_PREFIX = "taal_progress:";

/** One key per visitor id. */
export function crumbKey(visitorId: string): string {
  return `${CRUMB_KEY_PREFIX}${visitorId}`;
}

/** Tolerant: anything that is not the shape we write becomes "no progress" rather than an error. */
export function parseCrumbs(raw: string | null | undefined): Crumbs {
  if (!raw) return EMPTY_CRUMBS;
  try {
    const v = JSON.parse(raw) as Record<string, unknown>;
    if (!v || typeof v !== "object") return EMPTY_CRUMBS;
    const approved = Array.isArray(v.approved)
      ? v.approved.filter(
          (a): a is ApprovedCrumb =>
            !!a && typeof a === "object" && typeof (a as ApprovedCrumb).play_id === "string" && typeof (a as ApprovedCrumb).gap_id === "string",
        )
      : [];
    const fastForwarded = Array.isArray(v.fastForwarded) ? v.fastForwarded.filter((x): x is string => typeof x === "string") : [];
    return { spot: v.spot === true, plan: v.plan === true, offer: v.offer === true, approved, fastForwarded };
  } catch {
    return EMPTY_CRUMBS;
  }
}

export function serializeCrumbs(c: Crumbs): string {
  return JSON.stringify(c);
}

/** Adds an approval (once per play id). */
export function withApproved(c: Crumbs, a: ApprovedCrumb): Crumbs {
  if (c.approved.some((x) => x.play_id === a.play_id)) return c;
  return { ...c, approved: [...c.approved, a] };
}

/** Records that the fast-forward ran for a play (once per play id). */
export function withFastForwarded(c: Crumbs, playId: string): Crumbs {
  if (c.fastForwarded.includes(playId)) return c;
  return { ...c, fastForwarded: [...c.fastForwarded, playId] };
}

/** The minimal Storage surface used here, so tests can pass a Map-backed fake. */
export interface CrumbStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function readCrumbs(storage: CrumbStorage | null, visitorId: string): Crumbs {
  if (!storage) return EMPTY_CRUMBS;
  try {
    return parseCrumbs(storage.getItem(crumbKey(visitorId)));
  } catch {
    return EMPTY_CRUMBS;
  }
}

export function writeCrumbs(storage: CrumbStorage | null, visitorId: string, c: Crumbs): void {
  if (!storage) return;
  try {
    storage.setItem(crumbKey(visitorId), serializeCrumbs(c));
  } catch {
    // Blocked or full storage: progress is then only what the API can say.
  }
}

export function clearCrumbs(storage: CrumbStorage | null, visitorId: string): void {
  if (!storage) return;
  try {
    storage.removeItem(crumbKey(visitorId));
  } catch {
    // nothing to clear
  }
}

// ---------- derived progress ----------

/** What the API said, as far as the stepper cares. null means "not known (yet)". */
export interface ApiFacts {
  plays: ReadonlyArray<{ play_id: string; gap_id: string; status: string }> | null;
  outcomes: ReadonlyArray<{ status: string; play_id?: string }> | null;
  /** /plays answered 404: the sandbox this browser used is gone. */
  playsNotFound: boolean;
  /** The approve call itself answered 404 for a play the visitor had approved. */
  approveNotFound: boolean;
}

export const NO_FACTS: ApiFacts = { plays: null, outcomes: null, playsNotFound: false, approveNotFound: false };

export interface Progress {
  spot: boolean;
  plan: boolean;
  approve: boolean;
  offer: boolean;
  measure: boolean;
  /** The crumbs say the visitor approved, but the API says otherwise: the demo server restarted. */
  restarted: boolean;
  /** Measure is "unknown", not "not done", when /outcomes did not answer. */
  measureUnknown: boolean;
}

/** A play that has been approved, or has moved on from approval (running, measured). */
export function isApproved(status: string): boolean {
  return status !== "proposed" && status !== "rejected";
}

export function deriveProgress(heroGapId: string, crumbs: Crumbs, api: ApiFacts): Progress {
  const plays = api.plays;
  const heroHasPlay = plays?.some((p) => p.gap_id === heroGapId) ?? false;
  // When the tenant has no play for the hero gap, an approval of any play is what Approve means.
  const approvedByApi = plays ? plays.some((p) => isApproved(p.status) && (heroHasPlay ? p.gap_id === heroGapId : true)) : false;
  const heroCrumb = crumbs.approved.some((a) => (heroHasPlay || plays === null ? a.gap_id === heroGapId : true));

  // The demo server keeps sandboxes in memory, so a restart wipes the visitor's approvals while
  // this browser still remembers them. Evidence of that: a play the crumbs say was approved is
  // listed as "proposed" again, or /plays (or Approve) answered 404 for a visitor who had approved
  // something. A play that is merely absent from the list proves nothing (a live run's play may
  // not be listed), and "running" or "measured" is further along than approved, not a reset.
  const contradicted =
    plays !== null && crumbs.approved.some((a) => plays.some((p) => p.play_id === a.play_id && p.status === "proposed"));
  const gone = crumbs.approved.length > 0 && (api.playsNotFound || api.approveNotFound);
  const restarted = contradicted || gone;

  const approve = approvedByApi || (heroCrumb && plays === null && !api.playsNotFound && !api.approveNotFound);
  // Measure is done only by a measured row for a play THIS visitor approved: the seeded examples
  // that ship measured (and every other visitor's rows) say nothing about this session. A row with no
  // play id (a test fixture) counts as before.
  const approvedIds = new Set<string>(crumbs.approved.map((a) => a.play_id));
  for (const p of plays ?? []) if (isApproved(p.status)) approvedIds.add(p.play_id);
  const measured = api.outcomes?.some((o) => o.status === "measured" && (o.play_id === undefined || approvedIds.has(o.play_id))) ?? false;

  return {
    spot: crumbs.spot,
    plan: !restarted && (crumbs.plan || approve),
    approve: approve && !restarted,
    offer: approve && !restarted && crumbs.offer,
    measure: approve && !restarted && measured,
    restarted,
    measureUnknown: api.outcomes === null,
  };
}

export interface StepView {
  id: StepId;
  state: StepState;
  /** True when the step's own work is finished, whether or not it is also the current one. */
  done: boolean;
  /** Why the step is locked, for the tooltip and the accessible name. Absent unless locked. */
  hint?: string;
  /** The same in two words, shown under the step in place of the persona. */
  shortHint?: string;
}

export const HINT_APPROVE_FIRST = "Approve a plan first";
export const HINT_RESTARTED = "Run the demo again from the start";

/** The five steps with their states. A locked step is still a link: the state only says what is
 * missing, and nothing here blocks navigation. */
export function stepViews(current: StepId | null, p: Progress): StepView[] {
  return STEP_IDS.map((id) => {
    const done = p[id];
    if (id === current) return { id, state: "current", done };
    if (p.restarted && id !== "spot") {
      return { id, state: "locked", done: false, hint: HINT_RESTARTED, shortHint: "Start again" };
    }
    if (done) return { id, state: "done", done };
    if ((id === "offer" || id === "measure") && !p.approve) {
      return { id, state: "locked", done, hint: HINT_APPROVE_FIRST, shortHint: "Approve first" };
    }
    return { id, state: "next", done };
  });
}

/** "Step 3 of 5: Approve", for the compact bar and screen readers. */
export function positionText(current: StepId | null): string {
  const i = current ? STEP_IDS.indexOf(current) : -1;
  return i < 0 ? "Taal demo" : `Step ${i + 1} of ${STEP_IDS.length}: ${STEPS[i].label}`;
}

/** The accessible name of a step's link: "Plan: Play Desk (Arjun), done". */
export function stepAccessibleName(step: StepDef, view: StepView): string {
  const base = `${step.label}: ${step.destination} (${step.persona})`;
  if (view.state === "done") return `${base}, done`;
  if (view.state === "locked" && view.hint) return `${base}, ${view.hint.toLowerCase()}`;
  return base;
}
