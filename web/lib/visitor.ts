// Per-visitor sandbox id (§5.6). Kept in localStorage so a visitor keeps the
// same OverlayStore namespace across reloads (services/api/sandbox.py,
// agents/gate/store.py); never sent anywhere but our own API.
const KEY = "taal_visitor";

function randomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `v-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getVisitorId(): string {
  if (typeof window === "undefined") return "server";
  try {
    const existing = window.localStorage.getItem(KEY);
    if (existing) return existing;
    const created = randomId();
    window.localStorage.setItem(KEY, created);
    return created;
  } catch {
    // Private window / blocked storage: fall back to a per-load id.
    return randomId();
  }
}

/** Starts a new sandbox for this browser: a new visitor id replaces the stored one (lib/session.ts, when the
 * API no longer has the old one). Returns the new id. */
export function replaceVisitorId(): string {
  const created = randomId();
  try {
    window.localStorage.setItem(KEY, created);
  } catch {
    // Storage blocked: ids are per load already (see getVisitorId), so there is nothing stale to replace.
  }
  return created;
}
