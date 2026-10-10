// Which demo customer a play's offer actually reaches. One rule for the Approve preview, the
// "Chat as ..." follow-up and the chat panel's default, so none of them promises an offer to
// someone outside the play's audience. Pure: unit-tested in node (tests/e2e/treated-persona.spec.ts).
// The names come from the customer list the API returns; none is written here.
import type { DemoCustomer, Play } from "./types";

type PlayTarget = Pick<Play, "target">;

/** True when the customer shops at one of the stores the play targets. */
export function inAudience(customer: Pick<DemoCustomer, "home_node_id">, play: PlayTarget | null | undefined): boolean {
  return Boolean(play) && play!.target.node_ids.includes(customer.home_node_id);
}

/** The customer who gets the offer once `play` is approved: home store is one of the play's target
 * stores and role is not holdout. The one already selected wins when it qualifies. When nobody
 * qualifies the first non-holdout customer is returned (the already selected one if it is not a
 * holdout), and null when the list holds only holdout customers or is empty. */
export function treatedCustomerFor(
  play: PlayTarget | null | undefined,
  customers: readonly DemoCustomer[],
  selectedId?: string | null,
): DemoCustomer | null {
  const open = customers.filter((c) => c.role !== "holdout");
  if (open.length === 0) return null;
  const selected = selectedId ? open.find((c) => c.customer_id === selectedId) : undefined;
  if (selected && inAudience(selected, play)) return selected;
  return open.find((c) => inAudience(c, play)) ?? selected ?? open[0];
}

/** "Meena" from "Meena K."; a customer is addressed by first name in buttons and captions. */
export function firstName(customer: Pick<DemoCustomer, "display_name">): string {
  return customer.display_name.trim().split(/\s+/)[0] || customer.display_name;
}
