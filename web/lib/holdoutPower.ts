// The power of the Tea holdout design, for the note under the Outcomes result card. Every number
// here is read from eval/raw/holdout_power_2026-10-14.json (primary case outputs.tea_organic) and
// tests/e2e/holdout-power.spec.ts reads that file from disk and asserts each value, so the page
// cannot drift from the committed file. It is a SIMULATION of the measurement design, not a result.
import { count } from "./format";

export const HOLDOUT_POWER = {
  source: "eval/raw/holdout_power_2026-10-14.json",
  /** inputs.design.treated and held_out */
  treated: 355,
  heldOut: 39,
  /** inputs.power and inputs.confidence, as percentages */
  powerPct: 80,
  confidencePct: 95,
  /** outputs.tea_organic.min_detectable_lift_pp_at_355_39 */
  minDetectableLiftPp: 12.38,
  /** the one lift the note resolves: outputs.tea_organic.total_n_for_lift_at_90_10_split["5pp"] */
  resolveLiftPp: 5,
  resolveTotalN: 1156,
} as const;

/** The note's sentence, with the numbers formatted for reading. */
export function powerLineText(p: typeof HOLDOUT_POWER = HOLDOUT_POWER): string {
  return (
    `The Tea beat's holdout (${count(p.treated)} treated, ${count(p.heldOut)} held out) is under-powered by design. ` +
    `At the seeded base rate it could only detect a lift of about ${p.minDetectableLiftPp.toFixed(1)} pp ` +
    `(${p.powerPct}% power, ${p.confidencePct}% confidence); resolving a ${p.resolveLiftPp} pp lift would take about ` +
    `${count(p.resolveTotalN)} orders at the same 90/10 split. A simulation of the measurement design, not a result.`
  );
}
