"use client";

import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { getOutcomes } from "../../lib/api";
import { inr, pct, formatDateTime } from "../../lib/format";
import type { Outcome } from "../../lib/types";

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

  useEffect(() => {
    getOutcomes().then(setOutcomes);
  }, []);

  return (
    <main className="page">
      <div className="card__header">
        <h2>Outcomes</h2>
        <Badge kind="live" detail="/outcomes" />
      </div>
      <p className="muted">Per play: treated vs holdout, lift with CI when measured, the CEO number.</p>
      {!outcomes ? (
        <p className="muted">Loading…</p>
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
