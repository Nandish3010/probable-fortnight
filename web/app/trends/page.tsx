"use client";

import { useEffect, useState } from "react";
import { Badge } from "../../components/Badge";
import { getTrends, postTrendsRecompute } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import type { StyleTrend, TrendsRecomputeResponse } from "../../lib/types";

export default function TrendsPage() {
  const [trends, setTrends] = useState<StyleTrend[] | null>(null);
  const [recomputing, setRecomputing] = useState(false);
  const [result, setResult] = useState<TrendsRecomputeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    return getTrends().then(setTrends);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function recompute() {
    setRecomputing(true);
    setError(null);
    try {
      const r = await postTrendsRecompute();
      setResult(r);
      await refresh();
    } catch {
      setError("Recompute failed.");
    } finally {
      setRecomputing(false);
    }
  }

  return (
    <main className="page">
      <div className="card__header">
        <h2>Style trends</h2>
        <Badge kind="synthetic" detail="/trends" />
      </div>
      <p className="muted">
        What customers have asked the stylist for, by store, garment, colour family and occasion --
        a count of chat asks, not a forecast. On this demo tenant the numbers are whatever the
        seeded generator and the demo script produced.
      </p>
      <div className="outcomes-measure">
        <button type="button" onClick={recompute} disabled={recomputing}>
          {recomputing ? "Recomputing…" : "Recompute trends"}
        </button>
        {result ? (
          <span className="muted"> {result.rows} row{result.rows === 1 ? "" : "s"} · {formatDateTime(result.computed_at)}</span>
        ) : null}
        {error ? <span className="error"> {error}</span> : null}
      </div>
      {!trends ? (
        <p className="muted">Loading…</p>
      ) : trends.length === 0 ? (
        <p className="muted">
          No style asks in the window yet. Ask the stylist twice for the same kind of thing, then
          click Recompute trends above.
        </p>
      ) : (
        <div className="outcomes-table-wrap">
          <table className="outcomes-table">
            <thead>
              <tr>
                <th>Store</th>
                <th>Garment</th>
                <th>Colour family</th>
                <th>Occasion</th>
                <th>Asks</th>
                <th>Customers</th>
                <th>Unfulfilled</th>
              </tr>
            </thead>
            <tbody>
              {trends.map((t) => (
                <tr key={`${t.node_id}-${t.garment_type}-${t.colour_family}-${t.occasion}`}>
                  <td>{t.node_id}</td>
                  <td>{t.garment_type ?? "–"}</td>
                  <td>{t.colour_family ?? "–"}</td>
                  <td>{t.occasion ?? "–"}</td>
                  <td>{t.asks}</td>
                  <td>{t.distinct_customers}</td>
                  <td>{t.unfulfilled_asks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
