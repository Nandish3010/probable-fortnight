export type Basis = "assumption" | "measured";

/** What a number rests on. Assumption: projected from the estimator before anything is measured.
 * Measured: computed from the holdout after Measure. Plain words, no colour, so it also reads in
 * greyscale and to a screen reader. */
export const BASIS_HELP: Record<Basis, string> = {
  assumption: "Projected from the estimator, before anything is measured.",
  measured: "Measured from the holdout, after Measure.",
};

export function BasisTag({ basis }: { basis: Basis }) {
  return (
    <span className={`basis basis--${basis}`} title={BASIS_HELP[basis]} data-testid={`basis-${basis}`}>
      {basis}
    </span>
  );
}
