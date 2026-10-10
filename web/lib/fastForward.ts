// Pure helpers for "fast-forward one day" (E2): who orders, what is said, and how a result is
// described. The sequence itself, which calls existing client functions only, is in
// components/FastForwardPanel.tsx. Unit-tested in node (tests/e2e/fast-forward.spec.ts).
import { count } from "./format";
import type { DemoCustomer, Outcome } from "./types";

export const FF_TITLE = "See what measuring looks like";
export const FF_BUTTON = "Fast-forward one day";
export const FF_ALREADY = "Already fast-forwarded in this session";
export const FF_EXPLAINER =
  "One order is far too few to prove an effect. This shows the loop working; a pilot would supply the real numbers.";

/** The customer who orders: a "sample" persona of the approved play (the treated side; the holdout
 * customer is never offered it), preferring one whose home store is a store the play targets. */
export function pickTreatedPersona(customers: readonly DemoCustomer[], nodeIds: readonly string[]): DemoCustomer | null {
  const samples = customers.filter((c) => c.role === "sample");
  return samples.find((c) => nodeIds.includes(c.home_node_id)) ?? samples[0] ?? null;
}

/** The chat session and message of the existing order flow: the same "add:<sku>" quick reply a
 * tapped button sends (tests/live/management.spec.ts). */
export function orderRequest(customerId: string, sku: string): { session_id: string; text: string } {
  return { session_id: `${customerId}:web`, text: `add:${sku}` };
}

export type FfStepId = "lookup" | "order" | "measure";

export function stepLabel(id: FfStepId, name: string): string {
  switch (id) {
    case "lookup":
      return "Finding a treated customer";
    case "order":
      return `Placing ${name}'s order`;
    case "measure":
      return "Measuring against the holdout";
  }
}

/** "1 treated customer ordered", from the measured row (never typed). */
export function sampleSizeLine(outcome: Outcome): string {
  const n = outcome.treated.responders;
  const h = outcome.holdout.responders;
  return `${count(n)} treated customer${n === 1 ? "" : "s"} ordered (of ${count(outcome.treated.customers)}); ${count(h)} of ${count(outcome.holdout.customers)} holdout customers ordered.`;
}
