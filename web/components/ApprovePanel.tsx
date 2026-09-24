"use client";

import { useState } from "react";
import { approve } from "../lib/api";
import { Badge } from "./Badge";
import { ForecastChart } from "./ForecastChart";
import { inr } from "../lib/format";
import type { ApproveResponse, Play } from "../lib/types";

export function ApprovePanel({
  play,
  holdoutFraction,
  rationale,
  onApproved,
}: {
  play: Play;
  holdoutFraction?: number;
  rationale?: string;
  onApproved?: (res: ApproveResponse) => void;
}) {
  const [result, setResult] = useState<ApproveResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function handleApprove() {
    setLoading(true);
    setError(false);
    try {
      const res = await approve({
        play_id: play.play_id,
        holdout_fraction: holdoutFraction,
        rationale,
      });
      setResult(res);
      onApproved?.(res);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="approve-panel">
      {!result ? (
        <button type="button" className="approve-button" onClick={handleApprove} disabled={loading}>
          {loading ? "Approving…" : "Approve"}
        </button>
      ) : (
        <div className="approve-panel__result" data-testid="approve-result">
          <div className="approve-panel__badges">
            <Badge
              kind={result.source === "live" ? "live" : "replay"}
              detail={
                result.source === "live"
                  ? `${result.forecast.model} · live · ${(result.forecast.latency_ms / 1000).toFixed(1)} s · ${result.forecast.run_id}`
                  : `showing recorded result · ${result.forecast.run_id}`
              }
            />
            <span className="chip">holdout {result.assignment.holdout_n} / treated {result.assignment.treated_n}</span>
          </div>
          <ForecastChart forecast={result.forecast} />
          <p className="approve-panel__writeoff" data-testid="writeoff-line">
            Projected write-off {inr(result.forecast.writeoff_before_inr)} {"→"} {inr(result.forecast.writeoff_after_inr)}
          </p>
          {error ? <p className="error">Live call failed; showing recorded result (live call failed).</p> : null}
        </div>
      )}
    </div>
  );
}
