// One place that turns a play's API fields into the figures every screen shows. Nothing here is
// hard-coded: re-record the flagship and every screen that calls playImpact() changes with it.
//
// Sign convention. The API's counterfactuals.do_nothing_inr and blanket_markdown_inr are POSITIVE
// losses (9200 = the lot written off). playImpact() returns NETS: negative means margin lost, so
// do_nothing_inr is -9200 and recovered_inr = play_net_inr - do_nothing_inr is a plain subtraction.
import { inr } from "./format";
import type { Counterfactuals, ExpectedOutcome, Mechanic } from "./types";

export type ComparisonKind = "beats" | "near_tie" | "markdown_retains_more";

export interface ImpactComponent {
  label: string;
  inr: number;
}

export interface PlayImpact {
  /** play_net_inr - do_nothing_inr: what the play recovers compared with doing nothing. The one
   * headline figure on every screen (ux_plan.md section 2). */
  recovered_inr: number;
  /** expected_outcome.waste_avoided_inr, at cost. */
  waste_avoided_inr: number;
  /** expected_outcome.margin_inr. For a transfer play this already contains the waste avoided. */
  margin_inr: number;
  /** Net of doing nothing: minus the lot written off. */
  do_nothing_inr: number;
  /** Net of a blanket markdown: minus the margin it destroys plus what is still written off. */
  blanket_inr: number;
  /** Net of the play: margin earned minus the lot still written off. */
  play_net_inr: number;
  /** The two parts that add up to recovered_inr, labelled for display. For a sales play: waste
   * avoided + margin. For a transfer: waste avoided - transfer cost (its margin already is that). */
  components: ImpactComponent[];
  comparison: {
    kind: ComparisonKind;
    /** play_net_inr - blanket_inr. Positive means the play keeps more. */
    delta_inr: number;
    copy: string;
  };
}

export interface ImpactInput {
  mechanic: Mechanic | string;
  expected_outcome: Pick<ExpectedOutcome, "margin_inr" | "waste_avoided_inr">;
  counterfactuals: Counterfactuals;
}

/** A gap difference smaller than this share of the amount at stake is treated as noise. */
export const NEAR_TIE_SHARE = 0.05;

const num = (v: number | null | undefined): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** The play's signed net against writing the lot off, derived locally. A transfer's margin is
 * "waste avoided minus transfer cost", so the avoided waste is already inside it and is not added
 * back (the old bar added it twice: Tea showed -19.8k, the right figure is -27.5k). Every other
 * mechanic's margin is sales margin only, so the avoided waste comes off the residual write-off. */
export function derivePlayNet(mechanic: string, margin: number, waste: number, doNothingLoss: number): number {
  return mechanic === "transfer_plus_nudge" ? margin - doNothingLoss : margin - (doNothingLoss - waste);
}

export function playImpact(play: ImpactInput, gap?: { rupees_at_stake?: number | null }): PlayImpact {
  const cf = play.counterfactuals;
  const margin = num(play.expected_outcome.margin_inr);
  const waste = num(play.expected_outcome.waste_avoided_inr);
  const doNothingLoss = num(cf.do_nothing_inr);
  const blanketLoss = num(cf.blanket_markdown_inr);
  const isTransfer = play.mechanic === "transfer_plus_nudge";

  const playNet =
    typeof cf.play_net_inr === "number" && Number.isFinite(cf.play_net_inr)
      ? cf.play_net_inr
      : derivePlayNet(String(play.mechanic), margin, waste, doNothingLoss);

  const doNothing = -doNothingLoss;
  const blanket = -blanketLoss;
  const recovered = playNet - doNothing;
  const delta = playNet - blanket;

  const atStake = num(gap?.rupees_at_stake) > 0 ? num(gap?.rupees_at_stake) : doNothingLoss;
  const pctLabel = `${Number.isFinite(cf.blanket_markdown_pct) ? Number(cf.blanket_markdown_pct) : 20}%`;

  let kind: ComparisonKind;
  let copy: string;
  if (Math.abs(delta) < NEAR_TIE_SHARE * atStake || delta === 0) {
    kind = "near_tie";
    copy = `Within noise of a blanket ${pctLabel} markdown, but only this play can be measured against a holdout`;
  } else if (delta > 0) {
    kind = "beats";
    copy = `Beats a blanket ${pctLabel} markdown by ${inr(delta)}`;
  } else {
    kind = "markdown_retains_more";
    copy = `A blanket ${pctLabel} markdown would retain ${inr(-delta)} more on this lot; this play keeps margin and can be measured`;
  }

  const components: ImpactComponent[] = isTransfer
    ? [
        { label: "Waste avoided (at cost)", inr: waste },
        { label: "Transfer cost", inr: margin - waste },
      ]
    : [
        { label: "Waste avoided (at cost)", inr: waste },
        { label: "Margin earned", inr: margin },
      ];

  return {
    recovered_inr: recovered,
    waste_avoided_inr: waste,
    margin_inr: margin,
    do_nothing_inr: doNothing,
    blanket_inr: blanket,
    play_net_inr: playNet,
    components,
    comparison: { kind, delta_inr: delta, copy },
  };
}

export interface AssignmentCounts {
  treated_n: number;
  holdout_n: number;
  eligible_n?: number;
  excluded_subscribers?: number;
}

/** The audience arithmetic, stated once: "354 consented, minus 2 subscribers, equals 352: 316
 * treated and 36 holdout". Null when the API did not send eligible_n (an older payload). */
export function audienceChain(a: AssignmentCounts): string | null {
  if (typeof a.eligible_n !== "number") return null;
  const split = `${a.treated_n} treated and ${a.holdout_n} holdout`;
  const excluded = a.excluded_subscribers ?? 0;
  if (excluded > 0) {
    const consented = a.eligible_n + excluded;
    return `${consented} consented, minus ${excluded} subscriber${excluded === 1 ? "" : "s"}, equals ${a.eligible_n}: ${split}`;
  }
  return `${a.eligible_n} consented: ${split}`;
}
