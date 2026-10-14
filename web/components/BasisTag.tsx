import { createElement, type HTMLAttributes, type ReactNode } from "react";
import type { PlanSource } from "../lib/types";

/** What a rupee figure rests on, in the words of the badge legend.
 * projected: estimator output on the seeded tenant (the headline, the bars, the portfolio).
 * synthetic: a seeded-tenant number (rupees at stake on a gap or an inbox row, synthetic orders).
 * recorded: a figure taken from a recorded Gemini run (its rationale, trace or cost).
 * measured: a holdout result after Measure; always shown together with SYNTHETIC, because the
 * orders it was measured on are simulated. */
export type BasisKind = "projected" | "synthetic" | "recorded" | "measured";

export const BASIS_LABEL: Record<BasisKind, string> = {
  projected: "PROJECTED",
  synthetic: "SYNTHETIC",
  recorded: "RECORDED",
  measured: "MEASURED",
};

export const BASIS_HELP: Record<BasisKind, string> = {
  projected: "Projected by the estimator on the seeded demo tenant. Not a measurement.",
  synthetic: "A number from the seeded demo tenant. No real customers, no pilot.",
  recorded: "Taken from a recorded Gemini run (its rationale, trace or cost), played back.",
  measured: "Measured against the holdout after Measure, over simulated orders.",
};

/** What a figure printed by a planner run rests on: RECORDED when the run is a recorded Gemini one
 * (its rationale, trace and cost are played back); otherwise the seeded tenant's own numbers. */
export function runBasis(source?: PlanSource | null): BasisKind {
  return source === "recorded_gemini" ? "recorded" : "synthetic";
}

/** The small outlined tag. Plain words, no colour, so it also reads in greyscale and to a screen
 * reader. "measured" always carries a SYNTHETIC tag beside it. */
export function BasisTag({ basis }: { basis: BasisKind }) {
  const tag = (
    <span className={`basis basis--${basis}`} title={BASIS_HELP[basis]} data-testid={`basis-${basis}`}>
      {BASIS_LABEL[basis]}
    </span>
  );
  if (basis !== "measured") return tag;
  return (
    <span className="basis-pair">
      {tag}
      <span className="basis basis--synthetic" title={BASIS_HELP.synthetic}>
        {BASIS_LABEL.synthetic}
      </span>
    </span>
  );
}

type BasisProps = Omit<HTMLAttributes<HTMLElement>, "children"> & {
  kind: BasisKind;
  /** The element to render; a div by default. */
  as?: "div" | "span" | "p" | "section" | "li" | "dd" | "td";
  /** Where the visible tag goes inside the container. "none" sets data-basis only: use it when a
   * tag next to it already covers the group, so a card carries one tag, not one per number. */
  tag?: "before" | "after" | "none";
  children?: ReactNode;
  "data-testid"?: string;
};

/** A container that says what the figures inside it rest on: it sets `data-basis="<kind>"` (the
 * rupee-labels spec asserts every text node with the rupee sign has such an ancestor) and renders
 * the tag once. The nearest container wins, so a card can be projected and one line inside it
 * synthetic. */
export function Basis({ kind, as = "div", tag = "before", children, ...rest }: BasisProps) {
  const label = tag === "none" ? null : <BasisTag basis={kind} />;
  return createElement(as, { ...rest, "data-basis": kind }, tag === "before" ? label : null, children, tag === "after" ? label : null);
}
