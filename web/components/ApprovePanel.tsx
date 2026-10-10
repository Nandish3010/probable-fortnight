"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { approve, getDemoCustomers, sendChat } from "../lib/api";
import { toApiError } from "../lib/apiError";
import {
  APPROVE_STEPS,
  TIMELINE,
  approveReducer,
  clockTime,
  initialApproveState,
} from "../lib/approveMachine";
import { chatUrlFor, DEMO_CUSTOMER_ID, DEMO_MESSAGE, requestChat } from "../lib/chatBridge";
import { inr } from "../lib/format";
import { audienceChain, playImpact } from "../lib/impact";
import { prefersReducedMotion } from "../lib/motion";
import { describeReply } from "../lib/previewReply";
import { firstName, treatedCustomerFor } from "../lib/treatedPersona";
import { recordApproved, reportSandboxGone } from "../lib/progressStore";
import type { ApproveResponse, ChatEnvelope, DemoCustomer, Play } from "../lib/types";
import styles from "./ApprovePanel.module.css";
import { ApproveSteps } from "./ApproveSteps";
import { ApproveToast } from "./ApproveToast";
import { Badge } from "./Badge";
import { Details } from "./Details";
import { ErrorCard } from "./ErrorCard";
import { ForecastChart } from "./ForecastChart";
import { label } from "../lib/labels";
import { Icon } from "./icons";
import { MeenaPreview, type PreviewState } from "./MeenaPreview";
import { RecoveredFigure } from "./RecoveredFigure";

/** How long the Meena preview waits for /chat before it says "Preview unavailable". */
export const PREVIEW_TIMEOUT_MS = 8000;
/** What the preview calls the customer until the demo-customer list says who the offer reaches. */
const PENDING_NAME = "the customer";
/** The name of the default demo customer, used only when the list cannot be read. */
const FALLBACK_NAME = "Meena";

const COUNT_UP = { delayMs: 0, durationMs: 900 } as const;

function sleep(ms: number): Promise<null> {
  return new Promise((resolve) => setTimeout(() => resolve(null), ms));
}

/**
 * Approve and everything that follows it (design_spec.md section 6). One reducer
 * (lib/approveMachine.ts) holds the phase: idle, submitting, animating, settled, error,
 * alreadyApproved. T0 is the moment the response arrives.
 *
 * Nothing here fakes progress. While the request is in flight all three step labels are "working"
 * and the timer counts real seconds; the ticks, the line draw, the count-up and the preview slide
 * all start at T0. Under prefers-reduced-motion the same information renders at once.
 */
export function ApprovePanel({
  play,
  holdoutFraction,
  rationale,
  productName,
  liveId = "approve-live",
  onApproved,
  onAlreadyApproved,
}: {
  play: Play;
  holdoutFraction?: number;
  rationale?: string;
  /** The product, for the result heading ("Approved: Darjeeling Tea 100G"). */
  productName?: string;
  /** The id of the announcement region. Unique per panel when a page holds several (the phone feed). */
  liveId?: string;
  onApproved?: (res: ApproveResponse) => void;
  /** Called when the play turns out to be approved already (a 409, or a status of approved). */
  onAlreadyApproved?: () => void;
}) {
  const router = useRouter();
  const [state, dispatch] = useReducer(
    approveReducer,
    undefined,
    () => initialApproveState({ alreadyApproved: play.status === "approved", approvedAt: play.approved_at ?? null }),
  );
  const [live, setLive] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [toastOpen, setToastOpen] = useState(false);
  const [preview, setPreview] = useState<PreviewState>({ status: "idle" });
  const [customer, setCustomer] = useState<DemoCustomer | null>(null);
  // False until the customer list has answered (or timed out), so the preview never names someone
  // before the play's own audience has been looked up.
  const [customerKnown, setCustomerKnown] = useState(false);

  const panelRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // A second click (or a key repeat) can land before React has re-rendered the button as
  // disabled; state alone would let it through. The ref flips synchronously, so exactly one
  // POST /approve is ever in flight per panel.
  const inFlight = useRef(false);
  const startedAt = useRef(0);
  const userInitiated = useRef(false);
  const toastDone = useRef(false);
  const previewStarted = useRef(false);
  const previewAbort = useRef<AbortController | null>(null);
  const announced30 = useRef(false);
  const alreadyNotified = useRef(false);

  const { phase } = state;
  const impact = playImpact(play);
  const result = state.result;
  const chain = result ? audienceChain(result.assignment) : null;
  const showButton = phase === "idle" || phase === "submitting" || phase === "error";
  const motionOn = state.animate;
  const approvedTime = clockTime(state.approvedAt);
  const customerName = customer ? firstName(customer) : customerKnown ? FALLBACK_NAME : PENDING_NAME;

  // ---- request ----

  async function handleApprove() {
    if (inFlight.current || (phase !== "idle" && phase !== "error")) return;
    inFlight.current = true;
    userInitiated.current = true;
    announced30.current = false;
    startedAt.current = performance.now();
    setSeconds(0);
    dispatch({ type: "submit" });
    try {
      const res = await approve({ play_id: play.play_id, holdout_fraction: holdoutFraction, rationale });
      const elapsedMs = performance.now() - startedAt.current;
      dispatch({ type: "respond", result: res, elapsedMs, reduced: prefersReducedMotion() });
      recordApproved(play);
      onApproved?.(res);
    } catch (e) {
      const error = toApiError(e, "/approve");
      // A 404 for a play this browser had approved means the demo server was restarted.
      if (error.kind === "not_found") reportSandboxGone(play.play_id);
      dispatch({ type: "fail", error, elapsedMs: performance.now() - startedAt.current });
    } finally {
      inFlight.current = false;
    }
  }

  // ---- the elapsed timer: real seconds from performance.now(), shown while the request is in flight ----

  useEffect(() => {
    if (phase !== "submitting") return;
    const id = setInterval(() => {
      const s = Math.floor((performance.now() - startedAt.current) / 1000);
      setSeconds(s);
      if (s >= 30 && !announced30.current) {
        announced30.current = true;
        setLive("Still working, 30 seconds. Taal waits up to 60 seconds.");
      }
    }, 250);
    return () => clearInterval(id);
  }, [phase]);

  // ---- the T0 timeline: ticks, collapse, reveal, chip, settle ----

  useEffect(() => {
    if (phase !== "animating") return;
    const ids: ReturnType<typeof setTimeout>[] = [];
    for (let i = 0; i < APPROVE_STEPS.length; i += 1) {
      ids.push(setTimeout(() => dispatch({ type: "tick" }), i * TIMELINE.tickEvery));
    }
    ids.push(setTimeout(() => dispatch({ type: "collapse" }), TIMELINE.collapse));
    ids.push(setTimeout(() => dispatch({ type: "reveal" }), TIMELINE.reveal));
    ids.push(setTimeout(() => dispatch({ type: "chip" }), TIMELINE.chip));
    ids.push(setTimeout(() => dispatch({ type: "settle" }), TIMELINE.settle));
    return () => ids.forEach(clearTimeout);
  }, [phase]);

  // ---- announcements (one persistent polite region) ----

  useEffect(() => {
    if (phase === "submitting") {
      setLive("Approving. This usually takes 10 to 13 seconds.");
    } else if (phase === "error") {
      // The ErrorCard is role="alert" and announces itself; saying it here as well would read it twice.
      setLive("");
    } else if (phase === "settled" && result) {
      const rupees = Math.round(impact.recovered_inr).toLocaleString("en-IN");
      setLive(
        `Approved. Recovered versus doing nothing: ${rupees} rupees. ${result.assignment.treated_n} customers will receive the offer; ${result.assignment.holdout_n} are held back.`,
      );
    } else if (phase === "alreadyApproved" && userInitiated.current) {
      setLive(`Already approved${approvedTime ? ` at ${approvedTime}` : ""}. Showing the recorded result.`);
    }
    // impact and approvedTime are derived from play/state and do not change within a phase.
  }, [phase]);

  useEffect(() => {
    if (phase === "animating" && state.stepsTicked > 0 && !state.collapsed) {
      setLive(`${APPROVE_STEPS[state.stepsTicked - 1]}: done.`);
    }
  }, [phase, state.stepsTicked, state.collapsed]);

  // ---- scrolling and focus ----

  // The steps sit under the button, which can be at the bottom of the screen: bring them into view
  // as the wait starts. At T0 the panel scrolls to the top of the screen (on a phone the sticky row
  // is released at that moment and the panel is further down the page), and once more when the
  // result body mounts and the page has grown to hold it.
  useEffect(() => {
    if (phase !== "submitting") return;
    const behavior = prefersReducedMotion() ? "auto" : "smooth";
    requestAnimationFrame(() => panelRef.current?.scrollIntoView({ block: "nearest", behavior }));
  }, [phase]);

  const past = phase === "animating" || phase === "settled" || phase === "alreadyApproved"; // T0 has happened
  useEffect(() => {
    if (!past || !userInitiated.current) return;
    const behavior = prefersReducedMotion() ? "auto" : "smooth";
    panelRef.current?.scrollIntoView({ block: "start", behavior });
  }, [past, state.bodyShown]);

  // Focus moves to the result heading once the sequence is over (the same pattern as the feedback
  // form's "Thank you" heading), never on a page load that already shows an approved play.
  useEffect(() => {
    if ((phase === "settled" || phase === "alreadyApproved") && userInitiated.current) {
      headingRef.current?.focus({ preventScroll: true });
    }
  }, [phase]);

  useEffect(() => {
    if (phase === "alreadyApproved" && !alreadyNotified.current) {
      alreadyNotified.current = true;
      if (userInitiated.current) recordApproved(play); // a 409 is an approval too: the server has it
      onAlreadyApproved?.();
    }
  }, [phase, onAlreadyApproved]);

  // ---- the toast ----

  useEffect(() => {
    if (state.chipShown && result && phase !== "alreadyApproved" && !toastDone.current) {
      toastDone.current = true;
      setToastOpen(true);
    }
  }, [state.chipShown, result, phase]);

  // ---- the Meena preview: the first real /chat reply, requested at T0, never blocking the result ----

  const loadPreview = useCallback(() => {
    previewAbort.current?.abort();
    const ctl = new AbortController();
    previewAbort.current = ctl;
    setPreview({ status: "loading" });

    let timer: ReturnType<typeof setTimeout> | undefined;
    (async () => {
      // Who gets this play's offer: a customer from the play's own audience (never a holdout one).
      // Meena is only in the chips audience, so asking her after a Tea approve would show "no offers".
      // The list is quick; if it does not answer in time the default demo customer is asked instead.
      const list = await Promise.race([getDemoCustomers(play.play_id).catch(() => null), sleep(1500)]);
      if (previewAbort.current !== ctl) return;
      const cust = list ? treatedCustomerFor(play, list) : null;
      setCustomer(cust);
      setCustomerKnown(true);
      const customerId = cust?.customer_id ?? DEMO_CUSTOMER_ID;

      const reply = new Promise<ChatEnvelope>((resolve, reject) => {
        sendChat(
          { session_id: `${customerId}:web`, text: DEMO_MESSAGE },
          (envelope) => {
            if (envelope.role === "agent" && envelope.text) resolve(envelope);
          },
          { timeoutMs: PREVIEW_TIMEOUT_MS, signal: ctl.signal },
        ).then(() => reject(new Error("no reply")), reject);
      });
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => {
          ctl.abort();
          reject(new Error("timeout"));
        }, PREVIEW_TIMEOUT_MS);
      });
      const envelope = await Promise.race([reply, timeout]);
      clearTimeout(timer);
      if (previewAbort.current !== ctl) return; // a newer request replaced this one
      const { language, offAudience } = describeReply(envelope, cust);
      setPreview({ status: "ready", envelope, language, offAudience });
    })().catch(() => {
      clearTimeout(timer);
      if (previewAbort.current === ctl) setPreview({ status: "failed" });
    });
    // `play` is read for its target stores; the play id identifies a new request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [play.play_id]);

  useEffect(() => {
    if (previewStarted.current) return;
    if (phase === "animating" || phase === "settled" || phase === "alreadyApproved") {
      previewStarted.current = true;
      loadPreview();
    }
  }, [phase, loadPreview]);

  useEffect(() => () => previewAbort.current?.abort(), []);

  // ---- follow-ups ----

  function chatAsCustomer() {
    const id = customer?.customer_id;
    if (!requestChat("prefill", DEMO_MESSAGE, id)) router.push(chatUrlFor("prefill", id));
  }
  function seeHoldout() {
    if (!requestChat("holdout", DEMO_MESSAGE)) router.push(chatUrlFor("holdout"));
  }

  // A 409 means it is already approved and a 404 means the sandbox was wiped: neither is fixed by
  // pressing Approve again, so a 404 gets no Retry (a 409 never reaches the error state).
  const retryable = state.error !== null && state.error.kind !== "not_found";

  // The figure is in the big number and the chip below; the heading says what was approved.
  const heading = `Approved: ${productName ?? label("sku", play.target.sku)}`;
  const recorded = phase === "alreadyApproved";

  return (
    <div
      ref={panelRef}
      className={`approve-panel ${styles.panel}`}
      data-phase={phase}
      aria-busy={phase === "submitting" ? true : undefined}
    >
      {/* Present from the first render so announcements register: submitting, each step, the result. */}
      <div id={liveId} className="visually-hidden" role="status" aria-live="polite" aria-atomic="true" data-testid="approve-live">
        {live}
      </div>

      {showButton ? (
        <div className={styles.buttonRow}>
          <button
            type="button"
            className="approve-button"
            onClick={handleApprove}
            disabled={phase === "submitting"}
            aria-busy={phase === "submitting"}
            data-testid="approve-button"
            data-tour="approve"
          >
            {phase === "submitting" ? "Approving…" : "Approve"}
          </button>
          {phase === "idle" ? (
            <span className={styles.hint} aria-hidden="true" data-testid="approve-hint">
              Press <kbd>A</kbd>
            </span>
          ) : null}
        </div>
      ) : (
        <div className={styles.approvedBar} data-testid="approved-bar">
          <Icon name="check" size={20} />
          <span>Approved{approvedTime ? ` at ${approvedTime}` : ""}</span>
        </div>
      )}

      {phase === "submitting" || phase === "animating" || phase === "settled" ? (
        <ApproveSteps
          ticked={state.stepsTicked}
          collapsed={state.collapsed}
          seconds={seconds}
          elapsedMs={state.elapsedMs}
        />
      ) : null}

      {/* A sibling of the button, so a failed POST /approve is actually visible and the judge can
         retry. The ErrorCard inside is role="alert", announced immediately (assertive). */}
      {phase === "error" && state.error ? (
        <div data-testid="approve-error" className={styles.error}>
          <ErrorCard error={state.error} onRetry={retryable ? handleApprove : undefined} />
        </div>
      ) : null}

      {recorded ? (
        <p className={styles.banner} data-testid="already-approved-banner">
          Already approved. Showing the recorded result.
        </p>
      ) : null}

      {state.bodyShown ? (
        <div className={styles.body} data-testid="approve-result" data-phase={phase} data-motion={motionOn ? "on" : "off"}>
          <h4 ref={headingRef} tabIndex={-1} className={styles.heading}>
            {heading}
          </h4>

          {result ? (
            <div className={styles.badges}>
              <Badge kind={result.source === "live" ? "live" : "replay"} />
              {chain === null ? (
                <span className="chip">holdout {result.assignment.holdout_n} / treated {result.assignment.treated_n}</span>
              ) : null}
            </div>
          ) : null}
          {chain !== null ? (
            <p className={styles.chain} data-testid="audience-chain">{chain}</p>
          ) : null}

          <RecoveredFigure
            impact={impact}
            testId="approve-recovered"
            countUp={{ run: phase === "animating", ...COUNT_UP }}
            chip={state.chipShown}
          />

          {result ? (
            <>
              <ForecastChart forecast={result.forecast} animate={motionOn && phase === "animating"} />
              <p className="approve-panel__writeoff" data-testid="writeoff-line">
                What-if write-off {inr(result.forecast.writeoff_before_inr)} {"→"} {inr(result.forecast.writeoff_after_inr)}
              </p>
              <p className="muted" data-testid="writeoff-caption">
                What-if forecast using the past promo lift. Not the play&apos;s own estimate.
              </p>
            </>
          ) : (
            <p className="muted" data-testid="recorded-forecast-note">
              The forecast chart from the first approval is not kept in this view.
            </p>
          )}

          <div className={styles.previewRow}>
            <MeenaPreview
              state={preview}
              name={customerName}
              animate={motionOn && phase === "animating"}
              onRetry={loadPreview}
            />
            <div className={`${styles.followups} ${motionOn && phase === "animating" ? styles.followupsIn : ""}`}>
              <button type="button" className={styles.follow} onClick={chatAsCustomer} data-testid="chat-as-customer">
                Chat as {customerName}
              </button>
              <button type="button" className={styles.follow} onClick={seeHoldout} data-testid="see-holdout">
                See what the holdout group sees
              </button>
            </div>
          </div>

          {result ? (
            <Details testId="approve-details">
              <dl className={styles.ids}>
                <dt>Play</dt>
                <dd>{result.play_id}</dd>
                <dt>Source</dt>
                <dd>{result.source === "live" ? "live" : "recorded result"}</dd>
                <dt>Forecast model</dt>
                <dd>{result.forecast.model}</dd>
                <dt>Forecast run</dt>
                <dd>
                  {result.forecast.run_id} · {(result.forecast.latency_ms / 1000).toFixed(1)} s
                </dd>
                <dt>Assignment seed</dt>
                <dd>{result.assignment.seed}</dd>
              </dl>
            </Details>
          ) : (
            <Details testId="approve-details">
              <dl className={styles.ids}>
                <dt>Play</dt>
                <dd>{play.play_id}</dd>
              </dl>
            </Details>
          )}
        </div>
      ) : null}

      {toastOpen && result ? (
        <ApproveToast
          message={`Approved. Taal will hold back ${result.assignment.holdout_n} customers to measure the result.`}
          onDone={() => setToastOpen(false)}
        />
      ) : null}
    </div>
  );
}
