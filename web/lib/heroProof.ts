// What the landing hero says about the flagship gap (components/HeroProof.tsx): the projected figure, the
// margin over a blanket markdown, and one line naming the user. Everything comes from the gap and play the
// page has loaded (lib/impact.ts, lib/labels.ts); until they have loaded, or when the API does not answer,
// it shows the recorded flagship's own values (Tea at Dark store 4, coordination/video/facts_and_numbers.md)
// so the first frame is never empty. Both are labelled PROJECTED / SYNTHETIC on screen.
import { inr, inrSigned, relativeDate } from "./format";
import { playImpact } from "./impact";
import { label } from "./labels";
import type { Gap, Play } from "./types";

export const HERO_FACTS = {
  recovered_inr: 9191,
  beat_inr: 6186,
  units: 103,
  days: 24,
  at_stake_inr: 35020,
  product: "Darjeeling tea",
} as const;

/** "Darjeeling Tea 100G" -> "Darjeeling tea": the pack size goes, only the first word keeps its capital. */
export function plainProduct(name: string): string {
  const base = name.replace(/\s+\d+(?:\.\d+)?\s?(?:g|kg|ml|l|pcs?)$/i, "").trim();
  const [first, ...rest] = base.split(/\s+/);
  return [first, ...rest.map((w) => w.toLowerCase())].join(" ");
}

function dayCount(n: number): string {
  return n === 1 ? "1 day" : `${n} days`;
}

export interface HeroProofData {
  /** "₹9,191". */
  recovered: string;
  /** "+₹6,186 vs a blanket markdown", or null when this play does not beat a blanket markdown. */
  beat: string | null;
  /** "A dark-store manager clearing 103 packs of Darjeeling tea, 24 days from sell-by, ₹35,020 at stake." */
  userLine: string;
}

export function heroProofData(gap?: Gap | null, play?: Play | null, now?: Date): HeroProofData {
  const impact = gap && play ? playImpact(play, gap) : null;
  const recovered = inrSigned(impact ? impact.recovered_inr : HERO_FACTS.recovered_inr);
  const beat = impact
    ? impact.comparison.kind === "beats"
      ? `+${inr(impact.comparison.delta_inr)} vs a blanket markdown`
      : null
    : `+${inr(HERO_FACTS.beat_inr)} vs a blanket markdown`;

  const rel = gap && now ? relativeDate(gap.deadline_date, now) : null;
  let userLine = `A dark-store manager clearing ${HERO_FACTS.units} packs of ${HERO_FACTS.product}, ${dayCount(HERO_FACTS.days)} from sell-by, ${inr(HERO_FACTS.at_stake_inr)} at stake.`;
  if (gap && rel) {
    const product = plainProduct(gap.evidence.sku_name ?? label("sku", gap.sku));
    const when = rel.days >= 0 ? `${dayCount(rel.days)} from sell-by` : `${dayCount(-rel.days)} past sell-by`;
    userLine = `A dark-store manager clearing ${gap.units_at_risk.toLocaleString("en-IN")} packs of ${product}, ${when}, ${inr(gap.rupees_at_stake)} at stake.`;
  }
  return { recovered, beat, userLine };
}
