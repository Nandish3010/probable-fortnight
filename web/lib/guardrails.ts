// A guardrail's API result is one boolean, `passed`. That hides a distinction the detail text
// makes: a rule can pass because it was checked and held, or "pass" because it had nothing to
// check (no stockout gap, no subscribers, an outlet shelf price with no personal message), or
// because the part it checks does not exist yet (the copy is written after Approve). Showing all
// of those as the same green tick overclaims, so the UI reads the detail text and shows three
// honest states. There is no API field for this; when the API grows one, replace the patterns.
import type { Guardrail } from "./types";

export type GuardrailState = "pass" | "not_applicable" | "pending" | "fail";

// Substrings of `detail`, lower-cased, as observed in the recorded plays (web/mocks/plays.json and
// fixtures/plays/valid). Order matters: "pending" is checked before "not applicable".
//   pending         "copy pending; best-before disclosure enforced at copy validation"
//   not applicable  "stockout rule not applicable", "disclosure not required", "consent not
//                   required", "no stockout gap for ...", "no active subscribers of ...",
//                   "... is not a discount play", "not a near-deadline play", and a frequency cap
//                   that checked nobody: "all 0 customers under 2 plays in 7 days"
const PENDING_PATTERNS = ["copy pending"];
const NOT_APPLICABLE_PATTERNS = [
  "not applicable",
  "not required",
  "no stockout gap",
  "no active subscribers",
  "not a discount play",
  "not a near-deadline play",
];

export function guardrailState(g: Pick<Guardrail, "passed" | "detail">): GuardrailState {
  if (!g.passed) return "fail";
  const detail = (g.detail ?? "").toLowerCase();
  if (PENDING_PATTERNS.some((p) => detail.includes(p))) return "pending";
  if (NOT_APPLICABLE_PATTERNS.some((p) => detail.includes(p))) return "not_applicable";
  if (/\ball 0 customers\b/.test(detail)) return "not_applicable";
  return "pass";
}

export interface GuardrailSummary {
  total: number;
  pass: number;
  not_applicable: number;
  pending: number;
  fail: number;
  /** "8 checks: 5 passed, 3 not applicable" (pending and failed are listed only when non-zero). */
  text: string;
}

export function summarizeGuardrails(guardrails: readonly Pick<Guardrail, "passed" | "detail">[]): GuardrailSummary {
  const counts = { pass: 0, not_applicable: 0, pending: 0, fail: 0 };
  for (const g of guardrails) counts[guardrailState(g)] += 1;
  const total = guardrails.length;
  const parts = [`${counts.pass} passed`];
  if (counts.not_applicable) parts.push(`${counts.not_applicable} not applicable`);
  if (counts.pending) parts.push(`${counts.pending} pending`);
  if (counts.fail) parts.push(`${counts.fail} failed`);
  return { total, ...counts, text: `${total} check${total === 1 ? "" : "s"}: ${parts.join(", ")}` };
}
