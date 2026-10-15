// A returning visitor whose browser still holds the id of a sandbox the API no longer has (the API
// restarted, or its disk was reset). The per-visitor reads (/plays, /outcomes, /customers/demo) can only
// answer 404 for that, and nothing the visitor can press would help, so the app starts a new sandbox on its
// own: a new visitor id, the old progress forgotten, the read sent again. Once per page load, so a server
// that answers 404 for everything cannot loop. lib/progressStore.ts listens and shows at most one calm note.
import { clearCrumbs, hasProgress, readCrumbs } from "./progress";
import { getVisitorId, replaceVisitorId } from "./visitor";

/** Reads that can only 404 because the visitor's sandbox is gone (never a gap, play or run id that is unknown). */
const SANDBOX_READS = new Set(["/plays", "/outcomes", "/customers/demo"]);

export function isSandboxRead(endpoint: string, method: string | undefined): boolean {
  return (method ?? "GET").toUpperCase() === "GET" && SANDBOX_READS.has(endpoint);
}

export interface SessionHealed {
  /** The old id had progress the visitor will notice is gone. */
  hadProgress: boolean;
}

const listeners = new Set<(e: SessionHealed) => void>();

export function onSessionHealed(listener: (e: SessionHealed) => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

let healed = false;

/** Starts a new sandbox. False when this page load has already done so (or there is no browser). */
export function healStaleSession(): boolean {
  if (healed || typeof window === "undefined") return false;
  healed = true;
  let storage: Storage | null = null;
  try {
    storage = window.localStorage;
  } catch {
    storage = null;
  }
  const old = getVisitorId();
  const hadProgress = hasProgress(readCrumbs(storage, old));
  clearCrumbs(storage, old);
  replaceVisitorId();
  listeners.forEach((l) => l({ hadProgress }));
  return true;
}
