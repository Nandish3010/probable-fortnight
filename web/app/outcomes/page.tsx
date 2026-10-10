"use client";

import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { CounterfactualBars } from "../../components/CounterfactualBars";
import { Details } from "../../components/Details";
import { ErrorCard } from "../../components/ErrorCard";
import { getOutcomes, getPlays, getPriorUpdate, isMockMode, postMeasure } from "../../lib/api";
import { toApiError, type ApiError } from "../../lib/apiError";
import { Skeleton } from "../../components/Skeleton";
import { count, dayMonth, inr, formatDateTime, liftInPoints, pct, pointsFromPp } from "../../lib/format";
import { GAP_TYPE_LABEL, label } from "../../lib/labels";
import { isApproved } from "../../lib/progress";
import { refreshProgress, useProgress } from "../../lib/progressStore";
import { recordedOutcomes } from "../../lib/recorded";
import type { MeasureResponse, Outcome, Play, PortfolioSummary, PriorUpdate } from "../../lib/types";
import portfolio from "../../mocks/portfolio_summary.json";
import styles from "./outcomes.module.css";

const PORTFOLIO: PortfolioSummary = portfolio as PortfolioSummary;

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
    <div className="card portfolio-card" data-testid="portfolio-card">
      <div className="card__header">
        <h2 className="card__title">Portfolio projection</h2>
        <Badge kind="synthetic" detail="batch job, not a live measurement" />
      </div>
      <p className="muted">
        Every gap Taal found in one scan of the stock ({dayMonth(PORTFOLIO.as_of)}), planned by the same rule-based
        drafter and estimator behind every play on this page. No model calls. This is a projection across the
        portfolio, not a measurement.
      </p>
      <div className="portfolio-card__stats">
        <div className="portfolio-card__stat">
          <span className="portfolio-card__number">{inr(totals.exposure_inr)}</span>
          <span className="portfolio-card__label">Total at stake</span>
          <span className="muted">across {count(totals.gaps)} gaps</span>
        </div>
        <div className="portfolio-card__stat">
          <span className="portfolio-card__number">{inr(planned.expected_margin_inr)}</span>
          <span className="portfolio-card__label">Expected recovered</span>
          <span className="muted">
            margin across {count(planned.count)} planned plays, with {inr(planned.expected_waste_avoided_inr)} of write-off
            avoided on {count(planned.expected_units)} units
          </span>
        </div>
        <div className="portfolio-card__stat">
          <span className="portfolio-card__number">{count(planned.count)}</span>
          <span className="portfolio-card__label">Plans drafted</span>
          <span className="muted">
            for {count(totals.gaps)} gaps; {count(planned.eligible_no_play)} more were eligible but no draft passed every check
          </span>
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
              <td>{count(v.count)}</td>
              <td>{inr(v.exposure_inr)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted portfolio-card__counterfactual-line">
        If nothing is done, this exposure becomes a {inr(totals.do_nothing_inr)} write-off. A blanket 20% markdown across
        every gap brings that to {inr(totals.blanket_markdown_inr)}. The planned plays are projected to recover{" "}
        {inr(planned.expected_margin_inr)} of margin without discounting volume that was not at risk.
      </p>
      <p className="muted portfolio-card__governor-line">
        Taal set aside {count(governor.triaged_out)} of {count(totals.gaps)} gaps before drafting anything:{" "}
        {inr(governor.triaged_out_exposure_inr)} of exposure, each below the {inr(governor.planner_threshold_inr)} planning
        threshold. No model or estimator cost was spent on them.
      </p>
      <Details summary="Details" testId="portfolio-details">
        Stock scan {PORTFOLIO.sense_run_id}, as of {PORTFOLIO.as_of}. Regenerate with python -m jobs.portfolio.
      </Details>
    </div>
  );
}

// Built once with the tenant (harness/prior_update_demo.py), so identical for every visitor and
// unchanged by Reset; shown only on the featured play's card.
function PriorUpdateLine({ update }: { update: PriorUpdate | null }) {
  if (!update) return null;
  const { before: b, after: a } = update;
  return (
    <div className="prior-update">
      <p>
        <strong>Estimator prior:</strong> Beta({b.alpha},{b.beta}) → Beta({a.alpha},{a.beta}) · <Badge kind="synthetic" /> orders
      </p>
      <p className="muted">
        One Measure run on synthetic orders: {update.responders.treated} of {update.treated_n} treated and{" "}
        {update.responders.holdout} of {update.holdout_n} holdout customers responded
        {update.lift != null && update.ci.low != null && update.ci.high != null ? (
          <>
            , {liftInPoints({ lift: update.lift, ci_low: update.ci.low, ci_high: update.ci.high })}
          </>
        ) : null}
        . The prior moves by exactly those treated counts. A demonstration of the update, not applied to the live
        estimator: no other play&apos;s estimate changes.
      </p>
    </div>
  );
}

function FeaturedCounterfactualCard({ play, priorUpdate }: { play: Play | null; priorUpdate: PriorUpdate | null }) {
  if (!play) return null;
  return (
    <div className="card">
      <div className="card__header">
        <h2 className="card__title">Worked example: {label("sku", play.target.sku)}</h2>
        <Badge kind="synthetic" />
      </div>
      <p className={styles.exampleNote} data-testid="seeded-example-note">
        <span>Seeded example, computed at build time. Not your approval.</span>
      </p>
      <p className="muted">
        {count(play.target.units)} units at {play.target.node_ids.map((n) => label("node", n)).join(", ")}, {inr(play.counterfactuals.do_nothing_inr)}{" "}
        written off if nothing is done.
      </p>
      <CounterfactualBars
        counterfactuals={play.counterfactuals}
        expectedOutcome={play.expected_outcome}
        mechanic={play.mechanic}
        blanketMarkdownGiveawayInr={BLANKET_MARKDOWN_GIVEAWAY_INR[play.play_id]}
      />
      {priorUpdate?.play_id === play.play_id ? <PriorUpdateLine update={priorUpdate} /> : null}
      <Details inline summary="Details" testId="worked-example-ids">
        {play.target.sku} · {play.play_id}. The derivation is in docs/impact_math.md.
      </Details>
    </div>
  );
}

const INCONCLUSIVE_TIP = "The interval crosses zero or too few customers responded";

/** Shown instead of a verdict when the measured difference cannot be told apart from noise. */
function InconclusiveBadge() {
  return (
    <span className="chip chip--inconclusive" title={INCONCLUSIVE_TIP} tabIndex={0} data-testid="inconclusive-badge">
      Inconclusive
      <span className="visually-hidden">: {INCONCLUSIVE_TIP}</span>
    </span>
  );
}

function ExpectedVsMeasured({ play, outcome }: { play: Play | null; outcome: Outcome | undefined }) {
  if (!play || !outcome || outcome.status !== "measured" || outcome.lift == null) return null;
  const crossesZero = (outcome.ci_low ?? 0) < 0 && (outcome.ci_high ?? 0) > 0;
  return (
    <p className="expected-vs-measured">
      <strong>Expected vs. measured, same play:</strong> the estimator projected{" "}
      {count(play.expected_outcome.units)} units; the holdout test measured {count(outcome.treated.units)} units
      in the treated group, a {liftInPoints(outcome)}
      {crossesZero ? ", a range that crosses zero" : ""}. {count(outcome.treated.customers + outcome.holdout.customers)}{" "}
      customers are too few to tell a real effect from noise. That is why the play above is labelled a projection and
      the row below is labelled measured: most tools stop at &quot;recommend&quot;, and this one measures and says so
      when the answer is null.
    </p>
  );
}

function ArmCell({ label, arm }: { label: string; arm: Outcome["treated"] }) {
  return (
    <td data-label={label}>
      <strong className="outcomes-table__arm-name">{label}</strong>
      <div className="muted">
        {count(arm.customers)} customers, {count(arm.responders)} responders, {count(arm.units)} units
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
        <span className="muted">of food kept out of the bin, across {measured.length} measured play{measured.length === 1 ? "" : "s"}</span>
      </div>
      <div className="impact-summary__stat">
        <span className="impact-summary__number">{co2e.toFixed(1)} kg CO2e</span>
        <span className="muted">of emissions avoided (an estimate)</span>
      </div>
      <div className="impact-summary__stat">
        <span className="impact-summary__number">{inr(rupees)}</span>
        <span className="muted">of margin kept that would otherwise have been written off</span>
      </div>
      <div className="impact-summary__details">
        <Details inline summary="Details" testId="impact-details">
          The emissions factor and its caveats are in docs/DATA_MODEL.md.
        </Details>
      </div>
    </div>
  );
}

/** The summary card is the first thing on the page: the measured result for the play THIS visitor
 * approved, or an honest empty state with the one button that produces it. The seeded portfolio and
 * worked example below it are labelled as not theirs. */
function SummaryCard({
  outcome,
  approvedName,
  loaded,
  measuring,
  onRun,
  measureResult,
}: {
  outcome: Outcome | undefined;
  /** Plain name of an approved play with no measured row yet, when there is one. */
  approvedName: string | null;
  loaded: boolean;
  measuring: boolean;
  onRun: () => void;
  measureResult: MeasureResponse | null;
}) {
  const crossesZero = outcome ? (outcome.ci_low ?? 0) < 0 && (outcome.ci_high ?? 0) > 0 : false;
  const inconclusive = outcome ? outcome.inconclusive === true : false;
  const lift = outcome ? outcome.lift_pp ?? (outcome.lift != null ? outcome.lift * 100 : null) : null;
  const lo = outcome ? outcome.ci_low_pp ?? (outcome.ci_low != null ? outcome.ci_low * 100 : null) : null;
  const hi = outcome ? outcome.ci_high_pp ?? (outcome.ci_high != null ? outcome.ci_high * 100 : null) : null;

  return (
    <section className={`card ${styles.summary}`} aria-labelledby="summary-title" data-testid="outcome-summary">
      <div className={styles.summaryHead}>
        <h2 id="summary-title">{outcome ? `Your result: ${label("sku", outcome.sku)}` : "Your result"}</h2>
        {outcome ? (
          <div className={styles.badges}>
            <Badge kind={outcome.data_label === "REAL PILOT" ? "real-pilot" : "synthetic"} />
            {inconclusive ? <InconclusiveBadge /> : null}
          </div>
        ) : null}
      </div>

      {outcome && lift != null ? (
        <>
          <div className={styles.figures}>
            <div className={styles.figure} data-testid="summary-difference">
              <span className={styles.figureLabel}>Response-rate difference, treated minus holdout</span>
              <span className={styles.figureValue}>{pointsFromPp(lift)} points</span>
              {lo != null && hi != null ? (
                <span className={styles.figureNote}>95% CI {pointsFromPp(lo)} to {pointsFromPp(hi)} points</span>
              ) : null}
            </div>
            <div className={styles.figure} data-testid="summary-ceo">
              <span className={styles.figureLabel}>CEO number: margin recovered per ₹1 of discount</span>
              {inconclusive ? (
                <span className={styles.figureValueMuted}>withheld: inconclusive</span>
              ) : outcome.margin_per_discount_rupee != null ? (
                <span className={styles.figureValue}>{outcome.margin_per_discount_rupee.toFixed(2)}</span>
              ) : (
                <span className={styles.figureValueMuted}>n/a: no discount was given</span>
              )}
              <span className={styles.figureNote}>net margin recovered per ₹1 of discount, against the holdout</span>
            </div>
          </div>
          <p className={styles.runNote}>
            {count(outcome.treated.customers)} customers got the offer and {count(outcome.holdout.customers)} were held back as the holdout.
            {outcome.treated.responders === 0 && outcome.holdout.responders === 0
              ? " Nobody in either group ordered yet, so this is a null result, not a failure: there is nothing to compare."
              : ""}
            {inconclusive || crossesZero
              ? ` The range crosses zero, so ${count(outcome.treated.customers + outcome.holdout.customers)} customers are too few to tell a real effect from noise.`
              : ""}
          </p>
        </>
      ) : (
        <div data-testid="summary-empty">
          <p className={styles.empty}>
            {!loaded ? "Checking your session…" : "Nothing is measured in your session yet. Approve a play, then Run Measure."}
          </p>
          {approvedName ? (
            <p className={styles.emptyHint}>
              You approved {approvedName}. Run Measure compares the customers who got the offer with the holdout group.
            </p>
          ) : null}
        </div>
      )}

      <div className={styles.runRow}>
        <button type="button" className="button-primary" onClick={onRun} disabled={measuring} data-testid="run-measure">
          {measuring ? "Measuring…" : "Run Measure"}
        </button>
        <p className={styles.runNote}>Nothing in your session is measured until you click Run Measure.</p>
      </div>
      {measureResult ? (
        <p className={styles.runNote} role="status" data-testid="measure-result">
          {measureResult.plays} play{measureResult.plays === 1 ? "" : "s"} joined against orders:{" "}
          {measureResult.measured} measured, {measureResult.unmeasured} unmeasured (below the minimum sample) ·{" "}
          {formatDateTime(measureResult.computed_at)}
        </p>
      ) : null}
    </section>
  );
}

export default function OutcomesPage() {
  const [outcomes, setOutcomes] = useState<Outcome[] | null>(null);
  const [featuredPlay, setFeaturedPlay] = useState<Play | null>(null);
  const [priorUpdate, setPriorUpdate] = useState<PriorUpdate | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const [measureResult, setMeasureResult] = useState<MeasureResponse | null>(null);
  const [measureError, setMeasureError] = useState<ApiError | null>(null);
  const [outcomesError, setOutcomesError] = useState<ApiError | null>(null);
  const [featuredError, setFeaturedError] = useState<ApiError | null>(null);
  const [priorError, setPriorError] = useState<ApiError | null>(null);
  const [usingRecorded, setUsingRecorded] = useState(false);

  async function loadOutcomes() {
    setOutcomesError(null);
    try {
      setOutcomes(await getOutcomes());
    } catch (e) {
      setOutcomesError(toApiError(e, "/outcomes"));
    }
  }

  async function loadFeatured() {
    setFeaturedError(null);
    try {
      const plays = await getPlays({ gap_id: "gap_chips_ds07" });
      setFeaturedPlay(plays.find((p) => p.play_id === FEATURED_PLAY_ID) ?? plays[0] ?? null);
    } catch (e) {
      setFeaturedError(toApiError(e, "/plays"));
    }
  }

  async function loadPrior() {
    setPriorError(null);
    try {
      setPriorUpdate(await getPriorUpdate());
    } catch (e) {
      setPriorUpdate(null);
      setPriorError(toApiError(e, "/outcomes/prior-update"));
    }
  }

  async function showRecordedOutcomes() {
    setOutcomes(await recordedOutcomes());
    setOutcomesError(null);
    setUsingRecorded(true);
  }

  useEffect(() => {
    loadOutcomes();
    loadFeatured();
    loadPrior();
  }, []);

  async function runMeasure() {
    setMeasuring(true);
    setMeasureError(null);
    try {
      const result = await postMeasure();
      setMeasureResult(result);
      // The sandbox may hold approvals this browser has no crumb for; ask it again so the summary
      // card can find the visitor's play.
      await Promise.all([loadOutcomes(), refreshProgress()]);
    } catch (e) {
      setMeasureError(toApiError(e, "/measure"));
    } finally {
      setMeasuring(false);
    }
  }

  const featuredOutcome = outcomes?.find((o) => o.play_id === FEATURED_PLAY_ID);

  // The play THIS visitor approved: the crumbs written by Approve, and the sandbox's own /plays.
  const progress = useProgress();
  const approvedIds = new Set<string>(progress.crumbs.approved.map((a) => a.play_id));
  for (const p of progress.api.plays ?? []) if (isApproved(p.status)) approvedIds.add(p.play_id);
  const mine = (outcomes ?? []).filter((o) => approvedIds.has(o.play_id));
  const myMeasured = mine.filter((o) => o.status === "measured" && o.lift != null);
  // The most recently approved play first; when the crumbs are silent, the first one the API reports.
  const order = progress.crumbs.approved.map((a) => a.play_id).reverse();
  const myOutcome =
    [...myMeasured].sort((a, b) => {
      const ia = order.indexOf(a.play_id);
      const ib = order.indexOf(b.play_id);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    })[0];
  const approvedPlayId = [...approvedIds][0];
  const approvedName = myOutcome || !approvedPlayId
    ? null
    : mine[0]
      ? label("sku", mine[0].sku)
      : featuredPlay && approvedIds.has(featuredPlay.play_id)
        ? label("sku", featuredPlay.target.sku)
        : "a play";

  return (
    <main id="main-content" tabIndex={-1} className="page">
      <div className="card__header">
        <h1>Outcomes</h1>
        <Badge kind={isMockMode() ? "replay" : "live"} detail="/outcomes" />
      </div>
      <p className="muted">
        Your measured result comes first. Below it: what the whole portfolio projects, one worked example, and every
        play that has been measured.
      </p>

      <SummaryCard
        outcome={myOutcome}
        approvedName={approvedName}
        loaded={outcomes !== null || outcomesError !== null}
        measuring={measuring}
        onRun={runMeasure}
        measureResult={measureResult}
      />
      {measureError ? (
        <ErrorCard
          error={measureError}
          compact
          onRetry={runMeasure}
          title={measureError.kind === "http" || measureError.kind === "not_found" ? "Measure did not run" : undefined}
          body={
            measureError.kind === "http" || measureError.kind === "not_found"
              ? "Approve a play first, then try again."
              : undefined
          }
        />
      ) : null}

      <PortfolioCard />
      {featuredError ? <ErrorCard error={featuredError} compact onRetry={loadFeatured} /> : null}
      <FeaturedCounterfactualCard play={featuredPlay} priorUpdate={priorUpdate} />
      {priorError ? <ErrorCard error={priorError} compact onRetry={loadPrior} /> : null}
      <ExpectedVsMeasured play={featuredPlay} outcome={featuredOutcome} />

      <h2 className={styles.sectionHead}>Measured plays</h2>
      <p className="holdout-explainer">
        <strong>Holdout</strong> is a randomly chosen control group: customers who get no offer for this play, picked
        the same way as everyone in &quot;Treated&quot; apart from a coin flip. Every response-rate difference below is
        what the treated group did minus what this control group did, not a before-and-after comparison of the same
        customers. That is the only honest way to know a play caused the change rather than a trend that was coming anyway.
      </p>
      {usingRecorded ? (
        <p className="muted" data-testid="recorded-note">
          <Badge kind="replay" detail="recorded copy" /> The live service is not answering, so these are the recorded
          rows that ship with the app.
        </p>
      ) : isMockMode() ? (
        <p className={styles.mockNote} data-testid="mock-rows-note">
          Replay mode: the rows below are recorded, not produced by your session.
        </p>
      ) : null}
      {outcomes ? <ImpactSummary outcomes={outcomes} /> : null}
      {outcomesError ? (
        <ErrorCard error={outcomesError} onRetry={loadOutcomes} onShowRecorded={showRecordedOutcomes} />
      ) : !outcomes ? (
        <div className={styles.skeletonRows} aria-busy="true" aria-label="Loading measured plays">
          <Skeleton height={56} radius={8} />
          <Skeleton height={56} radius={8} />
        </div>
      ) : outcomes.length === 0 ? (
        <p className="muted">
          No plays are measured yet. Approve a play on the Play Desk, then click Run Measure at the top of this page.
          Measure joins orders against the treated and holdout assignments.
        </p>
      ) : (
        <div className="outcomes-table-wrap" tabIndex={0} role="region" aria-label="Measured and unmeasured plays">
          <table className="outcomes-table">
            <thead>
              <tr>
                <th>Play</th>
                <th>Result</th>
                <th>CEO number</th>
                <th>Waste avoided</th>
                <th>Treated</th>
                <th>Holdout</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {outcomes.map((o) => (
                <tr key={o.play_id}>
                  <td data-label="Play" className="outcomes-table__play">
                    <strong>{label("sku", o.sku)}</strong>
                    <div className="muted">{label("node", o.node_id)} · {label("mechanic", o.mechanic)}</div>
                    {o.measured_at ? <div className="muted">Measured {formatDateTime(o.measured_at)}</div> : null}
                    <Details inline summary="Details">
                      {o.sku} · {o.node_id} · {o.mechanic} · {o.play_id} · minimum treated customers {o.min_treated_n}
                    </Details>
                  </td>
                  <td data-label="Result">
                    {o.status === "measured" && o.lift != null ? (
                      <span>
                        {liftInPoints(o) ?? pct(o.lift)}
                        {o.inconclusive === true ? (
                          <>
                            {" "}
                            <InconclusiveBadge />
                          </>
                        ) : null}
                      </span>
                    ) : (
                      <span className="muted">unmeasured</span>
                    )}
                  </td>
                  <td data-label="CEO number">
                    {o.inconclusive === true ? (
                      // An inconclusive result has no honest per-rupee figure: withheld, not zero.
                      <span className="muted" data-testid="ceo-withheld">withheld: inconclusive</span>
                    ) : o.status === "measured" && o.margin_per_discount_rupee != null ? (
                      <div>
                        <span className="ceo-number">{o.margin_per_discount_rupee.toFixed(2)}</span>
                        <div className="muted">net margin recovered per {"₹"}1 of discount vs holdout</div>
                      </div>
                    ) : o.status === "measured" ? (
                      <span className="muted">n/a: no discount was given</span>
                    ) : (
                      <span className="muted">unmeasured</span>
                    )}
                  </td>
                  <td data-label="Waste avoided">
                    {o.waste_avoided_inr != null ? inr(o.waste_avoided_inr) : "–"}
                    {o.waste_kg_est != null ? <div className="muted">{o.waste_kg_est.toFixed(1)} kg</div> : null}
                  </td>
                  <ArmCell label="Treated" arm={o.treated} />
                  <ArmCell label="Holdout" arm={o.holdout} />
                  <td data-label="Data">
                    <Badge kind={o.data_label === "REAL PILOT" ? "real-pilot" : "synthetic"} />
                    {o.looker_url ? (
                      <div>
                        <a href={o.looker_url} target="_blank" rel="noreferrer">
                          Open Looker
                        </a>
                      </div>
                    ) : null}
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
