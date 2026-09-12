// Per-visitor sandbox id (§5.6). Kept in localStorage so a visitor keeps the
// same Firestore namespace across reloads; never sent anywhere but our own API.
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
