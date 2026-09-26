"use client";

// Aggregates of real practitioner feedback, behind the admin token. The token is checked by the
// API (TAAL_FEEDBACK_ADMIN_TOKEN, from Secret Manager); this page only holds it in memory for the
// tab's lifetime and never renders contact details (the API never returns them).
//
// Form: one magnitude job per question -> single-series horizontal bars in one hue, every bar
// direct-labelled with its count (so no legend, and nothing is colour-only), inside a real table
// that doubles as the table view. Percentages appear only where the API supplied them (base >= 8).

import { useState } from "react";
import { FeedbackError, getFeedbackSummary } from "../../../lib/api";
import type { FeedbackModeSplit, FeedbackPctSplit, FeedbackQuestionSummary, FeedbackSummary } from "../../../lib/types";

function cell(c: FeedbackModeSplit, p?: FeedbackPctSplit): string {
  const one = (k: keyof FeedbackModeSplit) => (p && p[k] !== null ? `${c[k]} (${p[k]}%)` : String(c[k]));
  return `${one("total")} · self ${one("self")} · interview ${one("interview")}`;
}

function QuestionTable({ q, minN, caption }: { q: FeedbackQuestionSummary; minN: number; caption?: string }) {
  const opts = q.options ?? [];
  const max = Math.max(1, ...opts.map((o) => o.count.total));
  return (
    <div className="results__q">
      <h3>{caption ?? q.label}</h3>
      <p className="muted">
        Answered: {cell(q.answered)}
        {q.type === "multi" ? " · several options can be picked" : ""}
        {q.type === "scale" ? ` · median ${q.median ?? `not shown (fewer than ${minN} answers)`}` : ""}
      </p>
      <div className="outcomes-table-wrap" tabIndex={0} role="region" aria-label={q.label}>
        <table className="results__table">
          <thead>
            <tr>
              <th scope="col">Option</th>
              <th scope="col">All · self · interview</th>
            </tr>
          </thead>
          <tbody>
            {opts.map((o) => (
              <tr key={String(o.value)}>
                <th scope="row">{o.label}</th>
                <td>
                  <div className="results__barrow">
                    <span className="results__bar" aria-hidden="true" style={{ width: `${(100 * o.count.total) / max}%` }} />
                    <span className="results__val">{cell(o.count, o.pct)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function FeedbackResultsPage() {
  const [token, setToken] = useState("");
  const [summary, setSummary] = useState<FeedbackSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setSummary(await getFeedbackSummary(token));
    } catch (err) {
      setError(err instanceof FeedbackError ? err.message : "Could not load results.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page feedback results">
      <h1>Practitioner feedback: results</h1>
      {!summary ? (
        <form onSubmit={load} className="card">
          <div className="feedback__field">
            <label htmlFor="admin-token">Admin token</label>
            <input id="admin-token" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} aria-describedby={error ? "token-error" : undefined} aria-invalid={error ? true : undefined} />
          </div>
          <p id="token-error" className="error" role="alert">
            {error ?? ""}
          </p>
          <button type="submit" className="hero__cta" disabled={loading || !token}>
            {loading ? "Loading…" : "Show results"}
          </button>
        </form>
      ) : (
        <>
          <p className="muted">
            Real responses only ({summary.excluded_non_real} test row{summary.excluded_non_real === 1 ? "" : "s"} excluded). Every figure reads
            all · self · interview. <em>Interview</em> means a team member filled the form in during a call, which is weaker evidence than a
            practitioner filling it in alone. A percentage appears only where its base is at least {summary.min_n_for_percentages}. Quote numbers
            from the committed <code>harness.feedback_summary</code> output, not from this page.
          </p>
          <div className="results__kpis">
            {(["total", "self", "interview"] as const).map((k) => (
              <div key={k} className="card results__kpi">
                <span className="results__kpinum">{summary.responses[k]}</span>
                <span className="muted">{k === "total" ? "responses" : k === "self" ? "self-filled" : "interview-filled"}</span>
              </div>
            ))}
          </div>
          {summary.responses.total === 0 ? (
            <p className="card">No real responses yet.</p>
          ) : (
            <>
              <section aria-labelledby="h-questions">
                <h2 id="h-questions">Every question</h2>
                {Object.values(summary.questions)
                  .filter((q) => q.options)
                  .map((q) => (
                    <QuestionTable key={q.id} q={q} minN={summary.min_n_for_percentages} />
                  ))}
              </section>
              {Object.entries(summary.crosstabs).map(([by, groups]) => (
                <section key={by} aria-labelledby={`h-${by}`}>
                  <h2 id={`h-${by}`}>By {by === "a1_role" ? "role" : "business type"}</h2>
                  {groups.map((g) => (
                    <details key={g.value} className="card">
                      <summary>
                        {g.label} ({cell(g.n)})
                      </summary>
                      {Object.values(g.questions).map((q) => (
                        <QuestionTable key={q.id} q={q} minN={summary.min_n_for_percentages} />
                      ))}
                    </details>
                  ))}
                </section>
              ))}
              <section aria-labelledby="h-quotes">
                <h2 id="h-quotes">Quotes</h2>
                <p className="muted">Verbatim, only from respondents who agreed to be quoted, attributed by role and business type only.</p>
                {summary.quotes.length === 0 ? <p>None yet.</p> : null}
                {summary.quotes.map((x, i) => (
                  <figure key={i} className="card results__quote">
                    <blockquote>{x.text}</blockquote>
                    <figcaption className="muted">
                      {x.role}, {x.business} ({x.mode})
                    </figcaption>
                  </figure>
                ))}
              </section>
            </>
          )}
        </>
      )}
    </main>
  );
}
