"use client";

// Practitioner feedback form. The questions are data (config/feedback_form.json via
// GET /feedback/form), so wording changes need no code change here; this page only knows the
// question *types*. Deliberately not in the top navigation: it is reached from the landing footer
// or a shared link, and the judge's demo path does not pass through it.

import { useEffect, useMemo, useRef, useState } from "react";
import { FeedbackError, getFeedbackForm, submitFeedback } from "../../lib/api";
import type { FeedbackForm, FeedbackQuestion, FeedbackSubmission } from "../../lib/types";

type Value = string | number | string[] | undefined;
type Answers = Record<string, Value>;

function allQuestions(form: FeedbackForm): FeedbackQuestion[] {
  return form.sections.flatMap((s) => s.questions);
}

function isShown(q: FeedbackQuestion, visible: Record<string, unknown>): boolean {
  if (!q.show_if) return true;
  const v = visible[q.show_if.question];
  return typeof v === "string" && q.show_if.in.includes(v);
}

// The submitted answers: only questions that are currently shown, in form order, so a question
// hidden by an earlier choice (e.g. section C after "No" to c0) is never sent even if it was
// filled in before the choice changed. Visibility chains (c5 depends on c4, which depends on c0)
// resolve because each question is checked against the answers built so far.
function buildAnswers(form: FeedbackForm, a: Answers, contact: Record<string, string>, consent: boolean): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const q of allQuestions(form)) {
    if (!isShown(q, out)) continue;
    const v = a[q.id];
    if (q.type === "single" && typeof v === "string" && v) out[q.id] = v;
    if (q.type === "multi" && Array.isArray(v) && v.length) out[q.id] = v;
    if (q.type === "scale" && typeof v === "number") out[q.id] = v;
    if (q.type === "text" && typeof v === "string" && v.trim()) out[q.id] = v.trim();
    if (q.type === "contact") {
      const c: Record<string, string> = {};
      for (const f of q.fields ?? []) if (contact[f.id]?.trim()) c[f.id] = contact[f.id].trim();
      if (Object.keys(c).length) out[q.id] = c;
    }
    if (q.type === "consent" && consent) out[q.id] = true;
    if (q.other_id) {
      const picked = Array.isArray(v) ? v.includes("other") : v === "other";
      const text = a[q.other_id];
      if (picked && typeof text === "string" && text.trim()) out[q.other_id] = text.trim();
    }
  }
  return out;
}

function readParams(): { mode: "self" | "interview"; source: "real" | "test" } {
  if (typeof window === "undefined") return { mode: "self", source: "real" };
  const p = new URLSearchParams(window.location.search);
  return { mode: p.get("mode") === "interview" ? "interview" : "self", source: p.get("source") === "test" ? "test" : "real" };
}

export default function FeedbackPage() {
  const [form, setForm] = useState<FeedbackForm | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [params, setParams] = useState<{ mode: "self" | "interview"; source: "real" | "test" }>({ mode: "self", source: "real" });
  const [answers, setAnswers] = useState<Answers>({});
  const [contact, setContact] = useState<Record<string, string>>({});
  const [consent, setConsent] = useState(false);
  const [honeypot, setHoneypot] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const thanksRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    setParams(readParams());
    getFeedbackForm()
      .then(setForm)
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : "The form could not be loaded."));
  }, []);

  const built = useMemo(() => (form ? buildAnswers(form, answers, contact, consent) : {}), [form, answers, contact, consent]);
  const visible = useMemo(() => (form ? allQuestions(form).filter((q) => isShown(q, built)) : []), [form, built]);
  const answeredCount = visible.filter((q) => q.id in built).length;
  const pct = visible.length ? Math.round((100 * answeredCount) / visible.length) : 0;

  useEffect(() => {
    if (done) thanksRef.current?.focus();
  }, [done]);

  function set(id: string, v: Value) {
    setAnswers((prev) => ({ ...prev, [id]: v }));
    if (errors[id]) setErrors(({ [id]: _drop, ...rest }) => rest);
  }

  function toggle(q: FeedbackQuestion, value: string, checked: boolean) {
    const cur = (answers[q.id] as string[] | undefined) ?? [];
    set(q.id, checked ? [...cur, value] : cur.filter((x) => x !== value));
  }

  function validate(): Record<string, string> {
    const e: Record<string, string> = {};
    for (const q of visible) {
      if (q.required && !(q.id in built)) {
        e[q.id] = q.type === "consent" ? "Please tick the consent box to submit." : "Please choose an answer.";
      }
    }
    return e;
  }

  async function onSubmit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!form) return;
    const e = validate();
    setErrors(e);
    setSubmitError(null);
    if (Object.keys(e).length) {
      requestAnimationFrame(() => summaryRef.current?.focus());
      return;
    }
    const body: FeedbackSubmission = {
      form_version: form.form_version,
      mode: params.mode,
      source: params.source,
      answers: built as unknown as FeedbackSubmission["answers"],
      ...(honeypot ? { website: honeypot } : {}),
    };
    setSubmitting(true);
    try {
      const res = await submitFeedback(body);
      setDone(res.response_id);
      window.scrollTo({ top: 0 });
    } catch (err) {
      setSubmitError(err instanceof FeedbackError ? err.message : "Your response could not be saved. Please try again.");
      requestAnimationFrame(() => summaryRef.current?.focus());
    } finally {
      setSubmitting(false);
    }
  }

  if (done && form) {
    return (
      <main className="page feedback">
        <div className="card feedback__thanks">
          <h1 ref={thanksRef} tabIndex={-1}>
            {form.thank_you}
          </h1>
          <p>
            If you ever want your response deleted, quote this reference: <code data-testid="feedback-reference">{done}</code>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="page feedback">
      <h1>{form?.title ?? "Practitioner feedback"}</h1>
      {params.mode === "interview" ? (
        <p className="feedback__banner">Interview mode: a team member is filling this in during a call.</p>
      ) : null}
      {params.source === "test" ? (
        <p className="feedback__banner">Test mode: this response is marked as a test and excluded from all results.</p>
      ) : null}
      {loadError ? <p className="error" role="alert">{loadError}</p> : null}
      {!form ? (
        !loadError ? <p className="muted">Loading the form…</p> : null
      ) : (
        <form onSubmit={onSubmit} noValidate aria-describedby="feedback-intro">
          <p id="feedback-intro">
            {form.intro} About {form.estimated_minutes} minutes.
          </p>

          <div ref={summaryRef} tabIndex={-1} role="alert" className={Object.keys(errors).length || submitError ? "feedback__errors" : undefined}>
            {Object.keys(errors).length ? (
              <>
                <p>
                  <strong>Please fix {Object.keys(errors).length === 1 ? "this" : "these"} before submitting:</strong>
                </p>
                <ul>
                  {Object.entries(errors).map(([id, msg]) => {
                    const q = visible.find((x) => x.id === id);
                    return (
                      <li key={id}>
                        <a href={`#q-${id}`}>{q ? `${q.label} ${msg}` : msg}</a>
                      </li>
                    );
                  })}
                </ul>
              </>
            ) : submitError ? (
              <p>{submitError}</p>
            ) : null}
          </div>

          {form.sections.map((section) => {
            const qs = section.questions.filter((q) => isShown(q, built));
            return (
              <section key={section.id} className="card feedback__section" aria-labelledby={`sec-${section.id}`}>
                <h2 id={`sec-${section.id}`}>
                  <span className="feedback__secnum" aria-hidden="true">
                    {section.id}
                  </span>
                  {section.title}
                </h2>
                {section.intro ? <p className="muted">{section.intro}</p> : null}
                {section.show_description ? (
                  <div className="feedback__about">
                    {form.taal_description.map((t) => (
                      <p key={t}>{t}</p>
                    ))}
                    <p>
                      <a href={form.landing_url} target="_blank" rel="noreferrer">
                        See Taal&apos;s demo page (opens in a new tab)
                      </a>
                    </p>
                  </div>
                ) : null}
                {section.id === "E" ? (
                  <p id="consent-statement" className="feedback__consent-text">
                    {form.consent_statement}
                  </p>
                ) : null}
                {qs.map((q) => (
                  <Question
                    key={q.id}
                    q={q}
                    value={answers[q.id]}
                    otherValue={q.other_id ? (answers[q.other_id] as string | undefined) : undefined}
                    contact={contact}
                    consent={consent}
                    error={errors[q.id]}
                    onSingle={(v) => set(q.id, v)}
                    onToggle={(v, c) => toggle(q, v, c)}
                    onOther={(v) => q.other_id && set(q.other_id, v)}
                    onContact={(k, v) => setContact((p) => ({ ...p, [k]: v }))}
                    onConsent={(c) => {
                      setConsent(c);
                      if (c && errors[q.id]) setErrors(({ [q.id]: _drop, ...rest }) => rest);
                    }}
                  />
                ))}
              </section>
            );
          })}

          {/* Honeypot: people never see or reach this; a bot that fills it is discarded server-side. */}
          <div className="feedback__hp" aria-hidden="true">
            <label htmlFor="website">Leave this empty</label>
            <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" value={honeypot} onChange={(e) => setHoneypot(e.target.value)} />
          </div>

          <div className="feedback__footer">
            <div className="feedback__progress">
              <span id="progress-label">
                {answeredCount} of {visible.length} answered
              </span>
              <div
                className="feedback__bar"
                role="progressbar"
                aria-labelledby="progress-label"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={pct}
              >
                <div style={{ width: `${pct}%` }} />
              </div>
            </div>
            <button type="submit" className="hero__cta" disabled={submitting}>
              {submitting ? "Sending…" : "Submit"}
            </button>
          </div>
        </form>
      )}
    </main>
  );
}

interface QuestionProps {
  q: FeedbackQuestion;
  value: Value;
  otherValue?: string;
  contact: Record<string, string>;
  consent: boolean;
  error?: string;
  onSingle: (v: Value) => void;
  onToggle: (v: string, checked: boolean) => void;
  onOther: (v: string) => void;
  onContact: (k: string, v: string) => void;
  onConsent: (c: boolean) => void;
}

function Question({ q, value, otherValue, contact, consent, error, onSingle, onToggle, onOther, onContact, onConsent }: QuestionProps) {
  const errId = `err-${q.id}`;
  const hintId = `hint-${q.id}`;
  const preId = `pre-${q.id}`;
  const describedBy = [q.preamble ? preId : "", q.hint ? hintId : "", error ? errId : ""].filter(Boolean).join(" ") || undefined;
  const legend = (
    <>
      {q.label}
      {q.required ? <span className="feedback__req"> (required)</span> : null}
    </>
  );
  const errorLine = error ? (
    <p id={errId} className="error feedback__fielderror">
      {error}
    </p>
  ) : null;
  const hint = q.hint ? (
    <p id={hintId} className="muted feedback__hint">
      {q.hint}
    </p>
  ) : null;
  const preamble = q.preamble ? (
    <blockquote id={preId} className="feedback__preamble">
      {q.preamble}
    </blockquote>
  ) : null;

  if (q.type === "text") {
    const v = typeof value === "string" ? value : "";
    const countId = `count-${q.id}`;
    return (
      <div className="feedback__q" id={`q-${q.id}`}>
        <label htmlFor={`in-${q.id}`} className="feedback__label">
          {q.label}
        </label>
        <textarea
          id={`in-${q.id}`}
          rows={4}
          maxLength={q.max_length}
          value={v}
          aria-describedby={[countId, describedBy].filter(Boolean).join(" ")}
          onChange={(e) => onSingle(e.target.value)}
        />
        <p id={countId} className="muted feedback__hint">
          {v.length} of {q.max_length} characters
        </p>
      </div>
    );
  }

  if (q.type === "consent") {
    return (
      <div className="feedback__q" id={`q-${q.id}`}>
        <label className="feedback__choice feedback__choice--consent">
          <input
            type="checkbox"
            checked={consent}
            aria-invalid={error ? true : undefined}
            aria-describedby={["consent-statement", error ? errId : ""].filter(Boolean).join(" ")}
            onChange={(e) => onConsent(e.target.checked)}
          />
          <span>{legend}</span>
        </label>
        {errorLine}
      </div>
    );
  }

  if (q.type === "contact") {
    return (
      <fieldset className="feedback__q" id={`q-${q.id}`} aria-describedby={describedBy}>
        <legend className="feedback__label">{legend}</legend>
        {hint}
        {(q.fields ?? []).map((f) => (
          <div key={f.id} className="feedback__field">
            <label htmlFor={`in-${q.id}-${f.id}`}>{f.label}</label>
            <input
              id={`in-${q.id}-${f.id}`}
              type="text"
              maxLength={f.max_length}
              autoComplete={f.autocomplete}
              value={contact[f.id] ?? ""}
              onChange={(e) => onContact(f.id, e.target.value)}
            />
          </div>
        ))}
      </fieldset>
    );
  }

  if (q.type === "scale" && q.scale) {
    const { min, max, min_label, max_label } = q.scale;
    const values = Array.from({ length: max - min + 1 }, (_, i) => min + i);
    return (
      <fieldset className="feedback__q" id={`q-${q.id}`} aria-describedby={describedBy}>
        <legend className="feedback__label">{legend}</legend>
        {hint}
        <div className="feedback__scale">
          {values.map((n) => (
            <label key={n} className="feedback__scalebtn">
              <input type="radio" name={q.id} value={n} checked={value === n} onChange={() => onSingle(n)} aria-invalid={error ? true : undefined} />
              <span>
                {n}
                {n === min ? <span className="visually-hidden"> ({min_label})</span> : null}
                {n === max ? <span className="visually-hidden"> ({max_label})</span> : null}
              </span>
            </label>
          ))}
        </div>
        <div className="feedback__scaleends" aria-hidden="true">
          <span>{min_label}</span>
          <span>{max_label}</span>
        </div>
        {errorLine}
      </fieldset>
    );
  }

  const multi = q.type === "multi";
  const picked = multi ? ((value as string[] | undefined) ?? []) : [];
  const atMax = multi && q.max_select !== undefined && picked.length >= q.max_select;
  const otherPicked = multi ? picked.includes("other") : value === "other";
  return (
    <fieldset className="feedback__q" id={`q-${q.id}`} aria-describedby={describedBy}>
      <legend className="feedback__label">{legend}</legend>
      {preamble}
      {hint}
      <div className="feedback__choices">
        {(q.options ?? []).map((o) => {
          const checked = multi ? picked.includes(o.value) : value === o.value;
          return (
            <label key={o.value} className="feedback__choice">
              <input
                type={multi ? "checkbox" : "radio"}
                name={q.id}
                value={o.value}
                checked={checked}
                disabled={multi && atMax && !checked}
                aria-invalid={error ? true : undefined}
                onChange={(e) => (multi ? onToggle(o.value, e.target.checked) : onSingle(o.value))}
              />
              <span>{o.label}</span>
            </label>
          );
        })}
      </div>
      {q.other_id && otherPicked ? (
        <div className="feedback__field">
          <label htmlFor={`in-${q.other_id}`}>Please specify (optional)</label>
          <input id={`in-${q.other_id}`} type="text" maxLength={200} value={otherValue ?? ""} onChange={(e) => onOther(e.target.value)} />
        </div>
      ) : null}
      {errorLine}
    </fieldset>
  );
}
