"use client";

import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { getOutcomes, postMeasure } from "../../lib/api";
import { inr, pct, formatDateTime } from "../../lib/format";
import type { MeasureResponse, Outcome } from "../../lib/types";

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

export default function OutcomesPage() {
  const [outcomes, setOutcomes] = useState<Outcome[] | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const [measureResult, setMeasureResult] = useState<MeasureResponse | null>(null);
  const [measureError, setMeasureError] = useState<string | null>(null);

  function refresh() {
    return getOutcomes().then(setOutcomes);
  }

  useEffect(() => {
    refresh();
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

  return (
    <main className="page">
      <h1 className="visually-hidden">Taal</h1>
      <div className="card__header">
        <h2>Outcomes</h2>
        <Badge kind="live" detail="/outcomes" />
      </div>
      <p className="muted">Per play: treated vs holdout, lift with CI when measured, the CEO number.</p>
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
        <div className="outcomes-table-wrap">
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
                  <td>{o.waste_avoided_inr != null ? inr(o.waste_avoided_inr) : "–"}</td>
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
