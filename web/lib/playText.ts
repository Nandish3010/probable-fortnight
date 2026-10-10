// Plain-language sentences for the decision card, built from a play's and a gap's own fields.
// Nothing here names a SKU, a store or a mechanic: every word that is not template comes from the
// data (lib/labels.ts names the ids), so a re-recorded flagship or a different hero gap rewrites
// every card at once.
import { formatDate, inr, relativeDate } from "./format";
import { label } from "./labels";
import type { Gap, Play } from "./types";

/** "₹58.50", "₹61": two decimals only when the price has paise. */
export function rupees(value: number): string {
  return Number.isInteger(value) ? inr(value) : `₹${value.toFixed(2)}`;
}

export interface WhyNowInput {
  units: number;
  deadline_type: string;
  deadline_date: string;
  at_stake_inr: number;
}

/** What is at risk and by when, from the gap when there is one and from the play's own target
 * otherwise (the amount at stake is then the do-nothing loss). */
export function whyNowInput(play: Play, gap?: Gap | null): WhyNowInput {
  if (gap) {
    return {
      units: gap.units_at_risk,
      deadline_type: gap.deadline_type,
      deadline_date: gap.deadline_date,
      at_stake_inr: gap.rupees_at_stake,
    };
  }
  return {
    units: play.target.units,
    deadline_type: play.target.deadline_type,
    deadline_date: play.target.deadline_date,
    at_stake_inr: play.counterfactuals.do_nothing_inr,
  };
}

export interface WhyNow {
  /** "103 units pass their online sell-by in 24 days (6 Oct). ₹35,020 is at stake." */
  text: string;
  /** The deadline written out in full for a tooltip ("Tue 6 Oct 2026"), or null if it is not a date. */
  deadlineAbsolute: string | null;
}

/** One sentence: what is at risk, when it bites, and how much money is on it. `now` is the demo
 * clock from the server. Without it the deadline is written as a plain date: a relative phrase
 * against the browser's own clock would be wrong. */
export function whyNow(input: WhyNowInput, now?: Date): WhyNow {
  const rel = now ? relativeDate(input.deadline_date, now) : null;
  const when = rel
    ? rel.days > 60 || rel.days < -60
      ? `on ${rel.long}`
      : rel.long
    : `on ${formatDate(input.deadline_date)}`;
  const past = rel !== null && rel.days < 0;
  const units = `${input.units.toLocaleString("en-IN")} unit${input.units === 1 ? "" : "s"}`;
  let lead: string;
  switch (input.deadline_type) {
    case "online_sellby":
      lead = `${units} ${past ? "passed" : "pass"} their online sell-by ${when}.`;
      break;
    case "expiry":
      lead = `${units} ${past ? "reached" : "reach"} expiry ${when}.`;
      break;
    default:
      lead = `${units} at risk: the ${label("deadline", input.deadline_type).toLowerCase()} deadline is ${when}.`;
  }
  return {
    text: `${lead} ${inr(input.at_stake_inr)} is at stake.`,
    deadlineAbsolute: rel?.absolute ?? null,
  };
}

/** The mechanic in a sentence, from its own parameters. Unknown mechanics degrade to their label. */
export function mechanicSentence(play: Play, now?: Date): string {
  const p = play.mechanic_params;
  const sku = label("sku", play.target.sku);
  const nodes = play.target.node_ids.map((n) => label("node", n)).join(", ");
  switch (play.mechanic) {
    case "bundle":
      return p.bundle_sku
        ? `Offer a bundle of ${sku} with ${label("sku", p.bundle_sku)}${typeof p.bundle_price === "number" ? ` at ${rupees(p.bundle_price)}` : ""}`
        : `Offer ${sku} in a bundle`;
    case "transfer_plus_nudge":
      return p.transfer_to_node
        ? `Move ${typeof p.transfer_units === "number" ? `${p.transfer_units} units of ${sku}` : sku} from ${nodes} to ${label("node", p.transfer_to_node)}, then nudge customers there to buy them`
        : `Move ${sku} to a store where it sells, then nudge customers to buy it`;
    case "outlet_markdown":
      return typeof p.markdown_pct === "number"
        ? `Mark ${sku} down ${p.markdown_pct}% at ${nodes}`
        : `Mark ${sku} down at ${nodes}`;
    case "preorder": {
      const eta = relativeDate(p.preorder_eta_date, now);
      return `Take pre-orders for ${sku}${eta ? `; the next stock arrives ${eta.days > 60 ? `on ${eta.long}` : eta.long}` : ""}`;
    }
    case "coupon":
      return typeof p.discount_pct === "number" ? `Send a ${p.discount_pct}% coupon for ${sku}` : `Send a coupon for ${sku}`;
    case "usual_order_addon":
      return `Offer ${sku} as an add-on to the customer's usual order`;
    case "substitution":
      return `Offer ${sku} as a substitute for something that is out of stock`;
    case "subscription_nudge":
      return `Nudge customers who buy ${sku} often towards a subscription`;
    default:
      return `${label("mechanic", play.mechanic)}: ${sku}`;
  }
}

export interface AudienceEstimate {
  /** Customers who can be contacted: the audience after consent. */
  consented: number;
  /** Held back so the result can be measured (at least one when there is anyone to hold back). */
  holdout: number;
  treated: number;
  /** "about 291 of 323 consented customers get the offer; about 32 are held back to measure the result." */
  text: string;
}

/** The audience before Approve. The server draws the real split on Approve (it also drops active
 * subscribers from a discount), so this is an estimate and says "about". */
export function audienceEstimate(play: Play, fraction: number = play.holdout.fraction): AudienceEstimate {
  const consented = play.audience.size_after_consent;
  const holdout = consented > 0 ? Math.max(1, Math.round(consented * fraction)) : 0;
  const treated = Math.max(consented - holdout, 0);
  return {
    consented,
    holdout,
    treated,
    text: `About ${treated.toLocaleString("en-IN")} of ${consented.toLocaleString("en-IN")} consented customers get the offer; about ${holdout.toLocaleString("en-IN")} are held back to measure the result.`,
  };
}

/** The line under the chat's customer picker, from the hero play and what the API says about the
 * persona (its role for this play and its home store). It claims "treated" only when the data does:
 * a persona whose home store is one of the play's target stores. For anyone else it stays neutral. */
export function personaCaption(
  customer: { role: string; home_node_id?: string } | null | undefined,
  play: Play | null | undefined,
): string {
  if (customer?.role === "holdout") return "Holdout: never receives this offer, even after the play is approved.";
  if (!customer || !play) return "Receives the offer once the play is approved.";
  const inTarget = Boolean(customer.home_node_id) && play.target.node_ids.includes(customer.home_node_id as string);
  if (!inTarget) return "Receives the offer once the play is approved.";
  const product = label("sku", play.target.sku);
  const mechanic = label("mechanic", play.mechanic);
  return `In the treated group once you approve the ${product} play (${mechanic.charAt(0).toLowerCase()}${mechanic.slice(1)}).`;
}
