"use client";

// The browser side of the stepper's progress (lib/progress.ts holds the rules). One shared store,
// so the nav's stepper and the "demo restarted" banner read the same snapshot and the app asks
// /plays and /outcomes once, not once per component. React reads it with useSyncExternalStore.
//
// Crumbs are the only thing written, and only to this browser's localStorage, under the visitor id.
import { useSyncExternalStore } from "react";
import { getOutcomes, getPlays } from "./api";
import { ApiError } from "./apiError";
import { HERO_GAP_ID } from "./hero";
import {
  EMPTY_CRUMBS,
  NO_FACTS,
  clearCrumbs,
  deriveProgress,
  readCrumbs,
  withApproved,
  withFastForwarded,
  writeCrumbs,
  type ApiFacts,
  type Crumbs,
  type Progress,
} from "./progress";
import { getVisitorId } from "./visitor";

export interface ProgressSnapshot {
  crumbs: Crumbs;
  api: ApiFacts;
  progress: Progress;
  /** False until the crumbs have been read in the browser (the server render has none). */
  ready: boolean;
}

function snapshotOf(crumbs: Crumbs, api: ApiFacts, ready: boolean): ProgressSnapshot {
  return { crumbs, api, progress: deriveProgress(HERO_GAP_ID, crumbs, api), ready };
}

const SERVER_SNAPSHOT: ProgressSnapshot = snapshotOf(EMPTY_CRUMBS, NO_FACTS, false);

let snapshot: ProgressSnapshot = SERVER_SNAPSHOT;
const listeners = new Set<() => void>();
let inFlight: Promise<void> | null = null;
let refreshAgain = false;
// Plays approved in this page session whose approval a /plays read has not shown yet. A read that
// was already on its way when the approval landed would otherwise report the old status for a
// moment and the stepper would call a fresh approval a "restarted" demo.
const pendingApproved = new Set<string>();

function markApproved<T extends { play_id: string; status: string }>(plays: readonly T[] | null): T[] | null {
  if (!plays) return null;
  return plays.map((p) => {
    if (!pendingApproved.has(p.play_id)) return p;
    if (p.status === "approved") {
      pendingApproved.delete(p.play_id);
      return p;
    }
    return { ...p, status: "approved" };
  });
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function emit(next: ProgressSnapshot) {
  snapshot = next;
  listeners.forEach((l) => l());
}

function setCrumbs(crumbs: Crumbs) {
  writeCrumbs(storage(), getVisitorId(), crumbs);
  emit(snapshotOf(crumbs, snapshot.api, true));
}

function setApi(api: ApiFacts) {
  emit(snapshotOf(snapshot.crumbs, api, true));
}

/** Reads the crumbs from localStorage (first use, and after another tab wrote them). */
export function loadCrumbs() {
  emit(snapshotOf(readCrumbs(storage(), getVisitorId()), snapshot.api, true));
}

/** Asks /plays and /outcomes what the sandbox says. Concurrent calls share one round trip, and one
 * more runs afterwards if a change (an approval) arrived while it was in flight. */
export function refreshProgress(): Promise<void> {
  if (inFlight) {
    refreshAgain = true;
    return inFlight;
  }
  inFlight = (async () => {
    const facts: ApiFacts = { ...NO_FACTS };
    const [plays, outcomes] = await Promise.allSettled([getPlays(), getOutcomes()]);
    if (plays.status === "fulfilled") facts.plays = markApproved(plays.value);
    else if (plays.reason instanceof ApiError && plays.reason.kind === "not_found") facts.playsNotFound = true;
    if (outcomes.status === "fulfilled") facts.outcomes = outcomes.value;
    // An approve that answered 404 earlier stays remembered until the crumbs are cleared.
    facts.approveNotFound = snapshot.api.approveNotFound;
    setApi(facts);
  })().finally(() => {
    inFlight = null;
    if (refreshAgain) {
      refreshAgain = false;
      void refreshProgress();
    }
  });
  return inFlight;
}

/** Called once by whoever mounts first (the nav): reads crumbs, then the API. */
export function startProgress() {
  loadCrumbs();
  void refreshProgress();
}

// ---------- writers (each step's own screen calls the one for its step) ----------

function update(change: (c: Crumbs) => Crumbs) {
  const current = readCrumbs(storage(), getVisitorId());
  const next = change(current);
  if (next !== current) setCrumbs(next);
}

/** Priya confirmed rows on the phone view. */
export function recordSpot() {
  update((c) => (c.spot ? c : { ...c, spot: true }));
}

/** Arjun opened a play on the Desk. */
export function recordPlan() {
  update((c) => (c.plan ? c : { ...c, plan: true }));
}

/** A chat reply came back. */
export function recordOffer() {
  update((c) => (c.offer ? c : { ...c, offer: true }));
}

/** An approval succeeded. */
export function recordApproved(play: { play_id: string; gap_id: string }) {
  pendingApproved.add(play.play_id);
  const crumbs = withApproved(
    { ...readCrumbs(storage(), getVisitorId()), plan: true },
    { play_id: play.play_id, gap_id: play.gap_id, at: new Date().toISOString() },
  );
  writeCrumbs(storage(), getVisitorId(), crumbs);
  emit(snapshotOf(crumbs, { ...snapshot.api, plays: markApproved(snapshot.api.plays), approveNotFound: false }, true));
  void refreshProgress();
}

/** The fast-forward sequence finished for this play: its button is single-use from now on. */
export function recordFastForwarded(playId: string) {
  update((c) => withFastForwarded(c, playId));
}

/** Approve (or a read) answered 404 for a play the visitor had approved: the sandbox is gone. */
export function reportSandboxGone(playId: string) {
  const crumbs = readCrumbs(storage(), getVisitorId());
  if (!crumbs.approved.some((a) => a.play_id === playId)) return;
  pendingApproved.delete(playId);
  setApi({ ...snapshot.api, approveNotFound: true });
}

/** Reset demo data, or "Start again" on the restarted banner: forget this visitor's progress. */
export function clearProgress() {
  clearCrumbs(storage(), getVisitorId());
  pendingApproved.clear();
  emit(snapshotOf(EMPTY_CRUMBS, { ...snapshot.api, approveNotFound: false }, true));
  void refreshProgress();
}

// ---------- React ----------

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useProgress(): ProgressSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot, () => SERVER_SNAPSHOT);
}
