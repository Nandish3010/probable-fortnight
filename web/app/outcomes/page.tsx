"use client";

import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { CounterfactualBars } from "../../components/CounterfactualBars";
import { getOutcomes, getPlays, isMockMode, postMeasure } from "../../lib/api";
import { inr, formatDateTime, pct } from "../../lib/format";
import type { MeasureResponse, Outcome, Play, PortfolioSummary } from "../../lib/types";
import portfolio from "../../mocks/portfolio_summary.json";

const PORTFOLIO: PortfolioSummary = portfolio as PortfolioSummary;

const GAP_TYPE_LABEL: Record<string, string> = {
  online_sellby_breach: "online sell-by breaches",
  expiry_writeoff: "expiry write-offs",
  stockout_risk: "stockout risk",
  slow_mover: "slow movers",
  rebalance: "rebalance",
  assortment_gap: "assortment gaps",
  unmet_demand: "unmet demand",
};

// docs/impact_math.md, Part 1.2: the margin blanket_markdown_inr already destroys on the
// baseline volume that was projected to sell at full price with no intervention at all. Only
// known ahead of time for the featured play -- computing it for every play needs the same
// baseline-forecast lookup jobs/portfolio does, which this screen does not run live.
const BLANKET_MARKDOWN_GIVEAWAY_INR: Record<string, number> = {
  play_chips_ds07_v1: 433.38,
};

const FEATURED_PLAY_ID = "play_chips_ds07_v1";

function PortfolioCard() {
  const { totals, governor, planned } = PORTFOLIO;
  const byType = Object.entries(totals.by_type).sort((a, b) => b[1].exposure_inr - a[1].exposure_inr);
  return (
    <div className="card portfolio-card">
      <div className="card__header">
        <h3>Nightly portfolio</h3>
        <Badge kind="synthetic" detail="batch job, not a live measurement" />
      </div>
      <p className="muted">
        Every planner-eligible gap from one Sense run ({PORTFOLIO.sense_run_id}, as of{" "}
        {PORTFOLIO.as_of}), planned by the same deterministic drafter and estimator behind every
        play on this screen -- no model calls, run with{" "}
        <code>python -m jobs.portfolio</code>. This is a projection across the portfolio, not a
        measurement.
      </p>
      <div className="portfolio-card__stats">
        <div className="portfolio-card__stat">
          <span className="portfolio-card__number">{inr(totals.exposure_inr)}</span>
          <span className="muted">total exposure across {totals.gaps} gaps</span>
        </div>
        <div className="portfolio-card__stat">
          <span className="portfolio-card__number">{inr(planned.expected_margin_inr)}</span>
          <span className="muted">expected margin across {planned.count} planned plays</span>
        </div>
        <div className="portfolio-card__stat">
          <span className="portfolio-card__number">{inr(planned.expected_waste_avoided_inr)}</span>
          <span className="muted">expected waste avoided, {planned.expected_units.toLocaleString("en-IN")} units</span>
        </div>
      </div>
      <table className="portfolio-card__table">
        <thead>
          <tr>
            <th>Gap type</th>
            <th>Count</th>
            <th>Exposure</th>
          </tr>
        </thead>
        <tbody>
          {byType.map(([type, v]) => (
            <tr key={type}>
              <td>{GAP_TYPE_LABEL[type] ?? type}</td>
              <td>{v.count}</td>
              <td>{inr(v.exposure_inr)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted portfolio-card__counterfactual-line">
        Under do-nothing this exposure is a {inr(totals.do_nothing_inr)} write-off; a blanket 20%
        markdown across every gap brings that to {inr(totals.blanket_markdown_inr)}. Planned plays
        are projected to recover {inr(planned.expected_margin_inr)} of margin without discounting
        volume that was not at risk.
      </p>
      <p className="muted portfolio-card__governor-line">
        The Cost Governor triaged {governor.triaged_out} of {totals.gaps} gaps out before a play
        was attempted ({inr(governor.triaged_out_exposure_inr)} of exposure, each below the ₹
        {governor.planner_threshold_inr.toLocaleString("en-IN")} planner threshold -- a templated
        suggestion only, no model or estimator cost spent). {planned.eligible_no_play} more were
        eligible but produced no valid play (guardrails rejected every candidate).
      </p>
    </div>
  );
}

function FeaturedCounterfactualCard({ play }: { play: Play | null }) {
  if (!play) return null;
  return (
    <div className="card">
      <div className="card__header">
        <h3>Worked example: {play.target.sku}</h3>
        <Badge kind="synthetic" />
      </div>
      <p className="muted">
        {play.target.units} units at {play.target.node_ids.join(", ")}, {inr(play.counterfactuals.do_nothing_inr)}{" "}
        written off if nothing is done. See <code>docs/impact_math.md</code> for the full derivation.
      </p>
      <CounterfactualBars
        counterfactuals={play.counterfactuals}
        expectedOutcome={play.expected_outcome}
        blanketMarkdownGiveawayInr={BLANKET_MARKDOWN_GIVEAWAY_INR[play.play_id]}
      />
    </div>
  );
}

function ExpectedVsMeasured({ play, outcome }: { play: Play | null; outcome: Outcome | undefined }) {
  if (!play || !outcome || outcome.status !== "measured" || outcome.lift == null) return null;
  const crossesZero = (outcome.ci_low ?? 0) < 0 && (outcome.ci_high ?? 0) > 0;
  return (
    <p className="expected-vs-measured">
      <strong>Expected vs. measured, same play:</strong> the estimator projected{" "}
      {play.expected_outcome.units} units; the holdout test measured {outcome.treated.units} units
      in the treated arm, a lift of {pct(outcome.lift)}
      {outcome.ci_low != null && outcome.ci_high != null ? (
        <> (95% CI {pct(outcome.ci_low)}-{pct(outcome.ci_high)})</>
      ) : null}
      {crossesZero ? ", an interval that crosses zero" : ""} -- {outcome.treated.customers + outcome.holdout.customers}{" "}
      customers is too small a sample to resolve a real effect from noise. This is why the play
      above is labelled a projection and the row below is labelled measured: most tools stop at
      "recommend"; this one measures and reports when the answer is null.
    </p>
  );
}

function ArmCell({ label, arm }: { label: string; arm: Outcome["treated"] }) {
  return (
    <td>
      <strong>{label}</strong>
      <div className="muted">
        {arm.customers} customers, {arm.responders} responders, {arm.units} units
      </div>
      <div className="muted">margin {inr(arm.margin_inr)}, discount {inr(arm.discount_cost_inr)}</div>
    </td>
  );
}

function ImpactSummary({ outcomes }: { outcomes: Outcome[] }) {
  const measured = outcomes.filter((o) => o.status === "measured");
  if (measured.length === 0) return null;
  const kg = measured.reduce((sum, o) => sum + (o.waste_kg_est ?? 0), 0);
  const co2e = measured.reduce((sum, o) => sum + (o.co2e_kg_est ?? 0), 0);
  const rupees = measured.reduce((sum, o) => sum + (o.waste_avoided_inr ?? 0), 0);
  return (
    <div className="card impact-summary">
      <div className="impact-summary__stat">
        <span className="impact-summary__number">{kg.toFixed(1)} kg</span>
        <span className="muted">of food diverted from waste, across {measured.length} measured play{measured.length === 1 ? "" : "s"}</span>
      </div>
      <div className="impact-summary__stat">
        <span className="impact-summary__number">{co2e.toFixed(1)} kg</span>
        <span className="muted">CO2e avoided (estimate; see the emissions factor caveat in docs/DATA_MODEL.md)</span>
      </div>
      <div className="impact-summary__stat">
        <span className="impact-summary__number">{inr(rupees)}</span>
        <span className="muted">margin preserved that would otherwise have been written off</span>
      </div>
    </div>
  );
}

export default function OutcomesPage() {
  const [outcomes, setOutcomes] = useState<Outcome[] | null>(null);
  const [featuredPlay, setFeaturedPlay] = useState<Play | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const [measureResult, setMeasureResult] = useState<MeasureResponse | null>(null);
  const [measureError, setMeasureError] = useState<string | null>(null);

  function refresh() {
    return getOutcomes().then(setOutcomes);
  }

  useEffect(() => {
    refresh();
    getPlays({ gap_id: "gap_chips_ds07" }).then((plays) => {
      setFeaturedPlay(plays.find((p) => p.play_id === FEATURED_PLAY_ID) ?? plays[0] ?? null);
    });
  }, []);

  async function runMeasure() {
    setMeasuring(true);
    setMeasureError(null);
    try {
      const result = await postMeasure();
      setMeasureResult(result);
      await refresh();
    } catch {
      setMeasureError("Measure failed. Approve a play first, then try again.");
    } finally {
      setMeasuring(false);
    }
  }

  const featuredOutcome = outcomes?.find((o) => o.play_id === FEATURED_PLAY_ID);

  return (
    <main className="page">
      <h1 className="visually-hidden">Taal</h1>
      <div className="card__header">
        <h2>Outcomes</h2>
        <Badge kind={isMockMode() ? "replay" : "live"} detail="/outcomes" />
      </div>
      <p className="muted">
        Three views, in order: what the portfolio projects, what one play projects, and what one
        week of holdout measurement actually found.
      </p>

      <PortfolioCard />
      <FeaturedCounterfactualCard play={featuredPlay} />
      <ExpectedVsMeasured play={featuredPlay} outcome={featuredOutcome} />

      <div className="card__header">
        <h3>Measured</h3>
      </div>
      <p className="holdout-explainer">
        <strong>Holdout</strong> is a randomly assigned control group -- customers who see no offer for this
        play at all, chosen the same way as everyone in "Treated" except for a coin flip. Every lift number
        below is the difference between what the treated group actually did and what this control group did,
        not a before/after comparison against the same customers. This is the only honest way to know a play
        caused the change, rather than a trend that would have happened anyway.
      </p>
      {outcomes ? <ImpactSummary outcomes={outcomes} /> : null}
      <div className="outcomes-measure">
        <button type="button" onClick={runMeasure} disabled={measuring}>
          {measuring ? "Measuring…" : "Run Measure"}
        </button>
        {measureResult ? (
          <span className="muted">
            {" "}
            {measureResult.plays} play{measureResult.plays === 1 ? "" : "s"} joined against orders:{" "}
            {measureResult.measured} measured, {measureResult.unmeasured} unmeasured (below min treated n) ·{" "}
            {formatDateTime(measureResult.computed_at)}
          </span>
        ) : null}
        {measureError ? <span className="error"> {measureError}</span> : null}
      </div>
      {!outcomes ? (
        <p className="muted">Loading…</p>
      ) : outcomes.length === 0 ? (
        <p className="muted">
          No plays measured yet. Approve a play on the Play Desk, then click Run Measure above --
          this joins orders against treated/holdout assignments and is never run automatically.
        </p>
      ) : (
        <div className="outcomes-table-wrap" tabIndex={0} role="region" aria-label="Measured and unmeasured plays">
          <table className="outcomes-table">
            <thead>
              <tr>
                <th>Play</th>
                <th>Treated</th>
                <th>Holdout</th>
                <th>Lift</th>
                <th>Waste avoided</th>
                <th>CEO number</th>
                <th>Data</th>
                <th>Looker</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((o) => (
                <tr key={o.play_id}>
                  <td>
                    <strong>{o.sku}</strong>
                    <div className="muted">{o.node_id} · {o.mechanic}</div>
                    <div className="muted">
                      min treated n {o.min_treated_n}
                      {o.measured_at ? ` · measured ${formatDateTime(o.measured_at)}` : null}
                    </div>
                  </td>
                  <ArmCell label="Treated" arm={o.treated} />
                  <ArmCell label="Holdout" arm={o.holdout} />
                  <td>
                    {o.status === "measured" && o.lift != null ? (
                      <span>
                        {pct(o.lift)}
                        {o.ci_low !== undefined && o.ci_high !== undefined ? (
                          <span className="muted"> (CI {pct(o.ci_low)}–{pct(o.ci_high)})</span>
                        ) : null}
                      </span>
                    ) : (
                      <span className="muted">unmeasured</span>
                    )}
                  </td>
                  <td>
                    {o.waste_avoided_inr != null ? inr(o.waste_avoided_inr) : "–"}
                    {o.waste_kg_est != null ? <div className="muted">{o.waste_kg_est.toFixed(1)} kg</div> : null}
                  </td>
                  <td>
                    {o.status === "measured" && o.margin_per_discount_rupee != null ? (
                      <div>
                        <span className="ceo-number">{o.margin_per_discount_rupee.toFixed(2)}</span>
                        <div className="muted">net margin recovered per {"₹"}1 of discount vs holdout</div>
                      </div>
                    ) : (
                      <span className="muted">unmeasured</span>
                    )}
                  </td>
                  <td>
                    <Badge kind={o.data_label === "REAL PILOT" ? "real-pilot" : "synthetic"} />
                  </td>
                  <td>
                    {o.looker_url ? (
                      <a href={o.looker_url} target="_blank" rel="noreferrer">
                        Open Looker
                      </a>
                    ) : (
                      <button type="button" disabled>
                        Looker (n/a)
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
