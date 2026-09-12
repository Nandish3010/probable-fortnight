"use client";

import { useEffect, useMemo, useState } from "react";
import { ApprovePanel } from "../../components/ApprovePanel";
import { Badge } from "../../components/Badge";
import { CounterfactualBars } from "../../components/CounterfactualBars";
import { GAP_TYPE_LABEL } from "../../components/GapCard";
import { GuardrailList } from "../../components/GuardrailList";
import { PolicyEditor } from "../../components/PolicyEditor";
import { TracePanel } from "../../components/TracePanel";
import { getGaps, getPlays } from "../../lib/api";
import { formatDate, inr, pct } from "../../lib/format";
import type { Gap, Play } from "../../lib/types";

function runIdFromTraceRef(traceRef: string): string {
  return traceRef.startsWith("events/") ? traceRef.slice("events/".length) : traceRef;
}

export default function PlayDeskPage() {
  const [plays, setPlays] = useState<Play[]>([]);
  const [gapsById, setGapsById] = useState<Record<string, Gap>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");
  const [holdoutFraction, setHoldoutFraction] = useState(0.1);
  const [language, setLanguage] = useState<string>("en");
  const [showWhy, setShowWhy] = useState(false);
  const [rerunPlay, setRerunPlay] = useState<Play | null>(null);

  useEffect(() => {
    Promise.all([getPlays(), getGaps()]).then(([playList, gapList]) => {
      setPlays(playList);
      const byId: Record<string, Gap> = {};
      gapList.forEach((g) => {
        byId[g.gap_id] = g;
      });
      setGapsById(byId);
      if (playList.length > 0) setSelectedId(playList[0].play_id);
    });
  }, []);

  const rankedPlays = useMemo(
    () =>
      [...plays].sort(
        (a, b) => (gapsById[b.gap_id]?.rupees_at_stake ?? 0) - (gapsById[a.gap_id]?.rupees_at_stake ?? 0),
      ),
    [plays, gapsById],
  );

  const selected = plays.find((p) => p.play_id === selectedId) ?? null;

  useEffect(() => {
    if (selected) {
      setRationale(selected.rationale);
      setHoldoutFraction(selected.holdout.fraction);
      setLanguage(selected.copy.language_set[0] ?? "en");
      setShowWhy(false);
      setRerunPlay(null);
    }
  }, [selected]);

  const gap = selected ? gapsById[selected.gap_id] : undefined;

  return (
    <main className="page">
      <h2>Play Desk</h2>
      <div className="desk-layout">
        <div className="inbox" aria-label="Play inbox">
          {rankedPlays.map((p) => {
            const g = gapsById[p.gap_id];
            return (
              <button
                key={p.play_id}
                type="button"
                className={`inbox__item ${p.play_id === selectedId ? "inbox__item--active" : ""}`}
                onClick={() => setSelectedId(p.play_id)}
              >
                <strong>{g?.evidence.sku_name ?? p.target.sku}</strong>
                <div className="muted">{p.target.node_ids.join(", ")} · {p.mechanic}</div>
                <div>{inr(g?.rupees_at_stake ?? 0)} at stake</div>
              </button>
            );
          })}
          {rankedPlays.length === 0 ? <p className="muted">Loading plays…</p> : null}
        </div>

        <div>
          {!selected ? (
            <p className="muted">Select a play.</p>
          ) : (
            <div className="card" data-testid="play-detail">
              <div className="card__header">
                <div>
                  <h3>{gap?.evidence.sku_name ?? selected.target.sku}</h3>
                  <p className="muted">{selected.play_id} · status {selected.status}</p>
                </div>
                <Badge kind="replay" detail={`policy ${selected.policy_version}`} />
              </div>

              <section className="play-card__section">
                <h4>Target</h4>
                <p>
                  {selected.target.sku} · nodes {selected.target.node_ids.join(", ")} · {selected.target.units} units ·
                  deadline {formatDate(selected.target.deadline_date)} ({selected.target.deadline_type})
                </p>
                {gap ? <p className="muted">Gap type: {GAP_TYPE_LABEL[gap.type] ?? gap.type}</p> : null}
                {gap?.evidence.requests_count ? (
                  <p className="gap-card__demand">
                    {gap.evidence.requests_count} real chat request{gap.evidence.requests_count === 1 ? "" : "s"}
                    {gap.evidence.distinct_customers
                      ? ` from ${gap.evidence.distinct_customers} customer${gap.evidence.distinct_customers === 1 ? "" : "s"}`
                      : ""}{" "}
                    asking for this at this store
                  </p>
                ) : null}
              </section>

              <section className="play-card__section">
                <h4>Mechanic</h4>
                <p>{selected.mechanic} — {JSON.stringify(selected.mechanic_params)}</p>
              </section>

              <section className="play-card__section">
                <h4>Audience</h4>
                <p>
                  Segments: {selected.audience.segment_ids.join(", ")} — {selected.audience.size_before_consent} before consent
                  {" → "}
                  {selected.audience.size_after_consent} after consent
                </p>
              </section>

              <section className="play-card__section">
                <h4>Copy</h4>
                <div className="lang-toggle" role="group" aria-label="Language">
                  {selected.copy.language_set.map((lang) => (
                    <button
                      key={lang}
                      type="button"
                      aria-pressed={language === lang}
                      onClick={() => setLanguage(lang)}
                    >
                      {lang.toUpperCase()}
                    </button>
                  ))}
                </div>
                {selected.copy.variants
                  .filter((v) => v.language === language)
                  .map((v) => (
                    <p key={`${v.segment_id}-${v.language}`}>{v.text}</p>
                  ))}
              </section>

              <section className="play-card__section">
                <h4>Expected outcome</h4>
                <p>
                  {selected.expected_outcome.units} units · margin {inr(selected.expected_outcome.margin_inr)} ·
                  waste avoided {inr(selected.expected_outcome.waste_avoided_inr)} · discount cost{" "}
                  {inr(selected.expected_outcome.discount_cost_inr)}
                </p>
                <p className="muted">
                  CI {inr(selected.expected_outcome.ci_low)}–{inr(selected.expected_outcome.ci_high)} · prior n{" "}
                  {selected.expected_outcome.prior_n} · measured n {selected.expected_outcome.measured_n} ·{" "}
                  {selected.expected_outcome.estimator_version}
                </p>
              </section>

              <section className="play-card__section">
                <h4>Counterfactuals</h4>
                <CounterfactualBars
                  counterfactuals={selected.counterfactuals}
                  expectedOutcome={selected.expected_outcome}
                  holdout={selected.holdout}
                />
              </section>

              <section className="play-card__section">
                <h4>Guardrails</h4>
                <GuardrailList guardrails={selected.guardrails} />
              </section>

              <section className="play-card__section">
                <button type="button" onClick={() => setShowWhy((v) => !v)}>
                  {showWhy ? "Hide" : "Why this play?"}
                </button>
                {showWhy ? (
                  <div className="drawer">
                    {selected.alternatives.length === 0 ? (
                      <p className="muted">No alternatives recorded.</p>
                    ) : (
                      selected.alternatives.map((alt) => (
                        <div key={alt.mechanic} className="alt-card">
                          <strong>{alt.mechanic}</strong> — {JSON.stringify(alt.mechanic_params)}
                          <p className="muted">
                            expected {alt.expected_units} units, margin {inr(alt.expected_margin_inr)}
                          </p>
                          <p>Rejected because: {alt.rejected_because}</p>
                        </div>
                      ))
                    )}
                  </div>
                ) : null}
              </section>

              <section className="play-card__section">
                <h4>Rationale (editable)</h4>
                <textarea
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  rows={4}
                  aria-label="Rationale"
                />
              </section>

              <section className="play-card__section">
                <h4>Holdout fraction</h4>
                <input
                  type="range"
                  min={0.05}
                  max={0.5}
                  step={0.01}
                  value={holdoutFraction}
                  onChange={(e) => setHoldoutFraction(Number(e.target.value))}
                  aria-label="Holdout fraction"
                />
                <span> {pct(holdoutFraction, 0)}</span>
              </section>

              {selected.cost ? (
                <p className="muted">
                  Cost Governor: planned for {inr(selected.cost.plan_cost_inr)}; conversations budgeted{" "}
                  {inr(selected.cost.conversation_budget_inr)}; {selected.cost.pct_of_rupees_at_stake}% of rupees at stake.
                </p>
              ) : null}

              <ApprovePanel play={selected} holdoutFraction={holdoutFraction} rationale={rationale} />

              <section className="play-card__section">
                <h4>Trace</h4>
                <TracePanel runId={runIdFromTraceRef(selected.trace_ref)} />
              </section>

              <section className="play-card__section">
                <h4>Policy</h4>
                <PolicyEditor gapId={selected.gap_id} onReplan={setRerunPlay} />
              </section>

              {rerunPlay ? (
                <section className="play-card__section">
                  <h4>Re-plan result</h4>
                  <div className="drawer">
                    <p>
                      <strong>Old:</strong> {selected.mechanic} — {selected.rationale}
                    </p>
                    <p>
                      <strong>New ({rerunPlay.policy_version}):</strong> {rerunPlay.mechanic} — {rerunPlay.rationale}
                    </p>
                  </div>
                </section>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
