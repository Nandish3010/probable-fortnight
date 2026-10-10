"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ApprovePanel } from "./ApprovePanel";
import { Badge } from "./Badge";
import { CounterfactualBars } from "./CounterfactualBars";
import { Details } from "./Details";
import { GapCard } from "./GapCard";
import { GuardrailList } from "./GuardrailList";
import { RecoveredFigure } from "./RecoveredFigure";
import { SourceBadge } from "./SourceBadge";
import { formatDate, inr, inrSigned } from "../lib/format";
import { playImpact } from "../lib/impact";
import { GAP_TYPE_LABEL, label, labelList } from "../lib/labels";
import { audienceEstimate, mechanicSentence, whyNow, whyNowInput } from "../lib/playText";
import type { ApproveResponse, Gap, Play } from "../lib/types";
import styles from "./PlayCard.module.css";

export type PlayCardMode = "hero" | "detail" | "feed";

export interface PlayCardProps {
  play: Play;
  /** The gap the play answers. Without it the card falls back to the play's own target. */
  gap?: Gap | null;
  /** hero: the landing card. detail: the Desk. feed: the compact card of the phone feed (the feed
   * route itself is built later; the mode and its layout are reserved here). The content and the
   * order are identical in all three; the modes change density and where Approve sits. */
  mode?: PlayCardMode;
  /** The demo clock from the server (lib/useServerNow.ts). */
  now?: Date;
  /** Sent with Approve and used for the held-back estimate. Defaults to the play's own. */
  holdoutFraction?: number;
  /** The rationale as edited so far, sent with Approve (Desk). */
  rationale?: string;
  onApproved?: (res: ApproveResponse) => void;
  /** Shown next to the source badge (a "Live run" chip, a status). */
  badges?: ReactNode;
  /** Controls that belong beside the decision (the Desk's holdout slider), above Approve. */
  decisionExtra?: ReactNode;
  /** Replaces the read-only rationale inside Details (the Desk's editor). */
  whyThisPlay?: ReactNode;
  /** Desk-only sections that follow the card's Details (copy, trace, policy, re-plan results). */
  children?: ReactNode;
  /** Margin a blanket markdown gives away on volume that would have sold anyway, when known. */
  blanketMarkdownGiveawayInr?: number;
  testId?: string;
  /** The id of this card's Approve announcement region; unique per card when a page holds several. */
  liveId?: string;
}

/** The one decision card (design_spec.md section 5). Landing, Desk and phone all render this, from
 * playImpact() and the play's own fields, so the figure, the bars and the sentences cannot drift.
 *
 * Order, always: eyebrow, why now, the headline figure with its two parts, the three bars with the
 * computed comparison line, what Taal will do, the checks, Approve, Details.
 *
 * Approve is one button. On phones (< 768 px) its row is sticky to the bottom of the screen; on
 * the Desk, a bar under the nav offers a jump back to it once it has scrolled out of view. A
 * second Approve button would mean two controls for one irreversible act. */
export function PlayCard({
  play,
  gap = null,
  mode = "hero",
  now,
  holdoutFraction,
  rationale,
  onApproved,
  badges,
  decisionExtra,
  whyThisPlay,
  children,
  blanketMarkdownGiveawayInr,
  testId = "play-card",
  liveId,
}: PlayCardProps) {
  const titleId = useId();
  const decisionRef = useRef<HTMLDivElement>(null);
  const [approved, setApproved] = useState(play.status === "approved");
  const [pastDecision, setPastDecision] = useState(false);

  const impact = playImpact(play, { rupees_at_stake: gap?.rupees_at_stake });
  const fraction = holdoutFraction ?? play.holdout.fraction;
  const audience = audienceEstimate(play, fraction);
  const why = whyNow(whyNowInput(play, gap), now);
  const skuName = gap?.evidence.sku_name ?? label("sku", play.target.sku);
  const nodeNames = gap ? label("node", gap.node_id) : labelList("node", play.target.node_ids);
  const subLine = gap ? `${nodeNames} · ${GAP_TYPE_LABEL[gap.type] ?? gap.type}` : nodeNames;

  // The Desk bar shows once Approve has scrolled up out of view. Not before: a person who has not
  // reached the decision yet is not "past" it, and the bar would only cover the figure.
  // An IntersectionObserver reports the row entering and leaving the screen, and any layout shift
  // that moves it; it is silent when the row jumps from below the screen to above it in one frame
  // (End, a scrollTo, a long trackpad flick), because the state "not intersecting" did not change.
  // A passive scroll listener re-reads the position for that case.
  useEffect(() => {
    if (mode !== "detail" || approved) {
      setPastDecision(false);
      return;
    }
    const el = decisionRef.current;
    if (!el) return;
    const navHeight = 56;
    const check = () => setPastDecision(el.getBoundingClientRect().bottom <= navHeight);
    check();
    let io: IntersectionObserver | undefined;
    if (typeof IntersectionObserver !== "undefined") {
      io = new IntersectionObserver(check, { rootMargin: `-${navHeight}px 0px 0px 0px`, threshold: [0, 1] });
      io.observe(el);
    }
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      io?.disconnect();
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, [mode, approved]);

  function jumpToDecision() {
    const el = decisionRef.current;
    if (!el) return;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    el.querySelector<HTMLButtonElement>(".approve-button")?.focus({ preventScroll: true });
  }

  function handleApproved(res: ApproveResponse) {
    setApproved(true);
    onApproved?.(res);
  }

  // "A" jumps to Approve, only from inside this card and never while typing: the Desk's holdout
  // slider and rationale editor are inputs, so a key meant for them never gets here. It focuses the
  // button and does not press it: Enter or Space confirms. Only while the panel is idle.
  function handleKeyDown(e: KeyboardEvent<HTMLElement>) {
    if (e.defaultPrevented || e.repeat || e.key.toLowerCase() !== "a") return;
    if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    const target = e.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')) return;
    const panel = e.currentTarget.querySelector<HTMLElement>('[data-phase="idle"]');
    const button = panel?.querySelector<HTMLButtonElement>('[data-testid="approve-button"]');
    if (!button || button.disabled) return;
    e.preventDefault();
    button.focus();
  }

  const cls = [styles.card, styles[mode]].join(" ");
  const expected = play.expected_outcome;

  return (
    <article
      className={cls}
      data-testid={testId}
      data-mode={mode}
      data-a-hint=""
      aria-labelledby={titleId}
      onKeyDown={handleKeyDown}
    >
      {mode === "detail" ? (
        <div className={styles.barAnchor}>
          {pastDecision ? (
            <div className={styles.bar} role="region" aria-label="Decision bar" data-testid="decision-bar">
              <span className={styles.barFigure}>
                Recovered vs doing nothing <strong className="num">{inrSigned(impact.recovered_inr)}</strong>
              </span>
              <button type="button" className={styles.barButton} onClick={jumpToDecision}>
                Go to decision
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      <header className={styles.head}>
        <div className={styles.titleBlock}>
          <h3 id={titleId} className={styles.title} tabIndex={-1} data-card-title>
            {skuName}
          </h3>
          <p className={styles.sub}>{subLine}</p>
        </div>
        <div className={styles.badges}>
          {/* The play's own provenance (recorded Gemini run, scripted fixture, rules); REPLAY only when the API sent none. */}
          {play.source ? <SourceBadge source={play.source} /> : <Badge kind="replay" detail="Planner run recorded" />}
          {badges}
        </div>
      </header>

      <p
        className={styles.whyNow}
        data-testid="why-now"
        data-tour="why-now"
        title={why.deadlineAbsolute ? `Deadline: ${why.deadlineAbsolute}` : undefined}
      >
        {why.text}
      </p>

      <section className={styles.figure} aria-label="What the play recovers" data-tour="proof">
        <RecoveredFigure impact={impact} testId="recovered-figure" />
        <p className={styles.honesty} data-testid="honesty-line">
          A projection, not a measurement. About {audience.holdout.toLocaleString("en-IN")} customers are held back so the
          result can be measured.
        </p>
      </section>

      <section className={styles.section} aria-label="Compared with the alternatives" data-tour="proof">
        <CounterfactualBars
          counterfactuals={play.counterfactuals}
          expectedOutcome={play.expected_outcome}
          mechanic={play.mechanic}
          atStakeInr={gap?.rupees_at_stake}
          blanketMarkdownGiveawayInr={blanketMarkdownGiveawayInr}
          showFigure={false}
        />
      </section>

      <section className={styles.section}>
        <h4 className={styles.h4}>What Taal will do</h4>
        <p className={styles.plan} data-testid="plan-sentence">
          <strong>{label("mechanic", play.mechanic)}.</strong> {mechanicSentence(play, now)}. {audience.text}
        </p>
      </section>

      <div className={styles.checks} data-testid="card-checks">
        <GuardrailList guardrails={play.guardrails} />
      </div>

      {decisionExtra ? <div className={styles.extra}>{decisionExtra}</div> : null}

      <div
        ref={decisionRef}
        className={`${styles.decision} ${approved ? styles.decisionDone : ""}`}
        data-testid="decision"
        data-sticky={approved ? "off" : "on"}
      >
        {!approved ? (
          <span className={styles.stickyFigure} aria-hidden="true">
            <span className={styles.stickyAmount + " num"}>{inrSigned(impact.recovered_inr)}</span>
            <span className={styles.stickyLabel}>recovered</span>
          </span>
        ) : null}
        <div className={styles.approveSlot}>
          <ApprovePanel
            play={play}
            holdoutFraction={holdoutFraction}
            rationale={rationale}
            productName={skuName}
            liveId={liveId}
            onApproved={handleApproved}
            onAlreadyApproved={() => setApproved(true)}
          />
        </div>
      </div>

      <Details
        variant="card"
        testId="card-details"
        summary={
          <>
            Details <span className={styles.detailsHint}>why this play, who gets it, expected result, ids</span>
          </>
        }
      >
        <section className={styles.detailSection}>
          <h4 className={styles.h4}>Why now</h4>
          {gap ? (
            <GapCard gap={gap} now={now} variant="facts" />
          ) : (
            <p>
              {play.target.units} units · deadline {formatDate(play.target.deadline_date)}
            </p>
          )}
        </section>

        <section className={styles.detailSection}>
          <h4 className={styles.h4}>Why this play</h4>
          {whyThisPlay ?? <p data-testid="rationale-text">{play.rationale}</p>}
          {play.alternatives.length > 0 ? (
            <>
              <p className={styles.minor}>Alternatives the planner considered</p>
              <ul className={styles.alts} data-testid="alternatives">
                {play.alternatives.map((alt, i) => (
                  <li key={`${alt.mechanic}-${i}`}>
                    <strong>{label("mechanic", alt.mechanic)}</strong>: expected {alt.expected_units} units, margin{" "}
                    {inr(alt.expected_margin_inr)}. Rejected because: {alt.rejected_because}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>

        <section className={styles.detailSection}>
          <h4 className={styles.h4}>Who gets it</h4>
          <p>
            {labelList("segment", play.audience.segment_ids)}: {play.audience.size_before_consent} customers before consent,{" "}
            {play.audience.size_after_consent} after consent. The server draws the real split when you approve.
          </p>
        </section>

        <section className={styles.detailSection}>
          <h4 className={styles.h4}>Expected result</h4>
          <p>
            {expected.units} units · margin {inr(expected.margin_inr)} · waste avoided {inr(expected.waste_avoided_inr)} ·
            discount cost {inr(expected.discount_cost_inr)}
          </p>
          <p className={styles.minor}>
            Range {inr(expected.ci_low)}–{inr(expected.ci_high)} · prior n {expected.prior_n} · measured n{" "}
            {expected.measured_n} · {expected.estimator_version}
          </p>
          {play.cost ? (
            <p className={styles.minor}>
              Cost Governor: planned for {inr(play.cost.plan_cost_inr)}; conversations budgeted{" "}
              {inr(play.cost.conversation_budget_inr)}; {play.cost.pct_of_rupees_at_stake}% of rupees at stake.
            </p>
          ) : null}
        </section>

        <section className={styles.detailSection}>
          <h4 className={styles.h4}>Technical</h4>
          <dl className={styles.ids}>
            <dt>Play</dt>
            <dd data-testid="play-ids">
              {play.play_id} · {play.mechanic} · policy {play.policy_version}
            </dd>
            <dt>Gap</dt>
            <dd data-testid="gap-ids">
              {gap ? `${gap.sku} · ${gap.node_id} · ${gap.gap_id} · ${gap.type}` : `${play.target.sku} · ${play.gap_id}`}
            </dd>
            <dt>Target</dt>
            <dd data-testid="target-ids">
              {play.target.sku} · {play.target.node_ids.join(", ")} · {play.target.deadline_type}
            </dd>
            <dt>Mechanic</dt>
            <dd data-testid="mechanic-details">
              {play.mechanic} {JSON.stringify(play.mechanic_params)}
            </dd>
            <dt>Segments</dt>
            <dd data-testid="segment-ids">{play.audience.segment_ids.join(", ")}</dd>
            <dt>Trace</dt>
            <dd>{play.trace_ref}</dd>
          </dl>
        </section>
      </Details>

      {children}
    </article>
  );
}
