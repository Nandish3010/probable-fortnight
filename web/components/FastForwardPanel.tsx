"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Badge } from "./Badge";
import { ErrorCard } from "./ErrorCard";
import { getDemoCustomers, postMeasure, sendChat } from "../lib/api";
import { toApiError, type ApiError } from "../lib/apiError";
import { FF_ALREADY, FF_BUTTON, FF_TITLE, orderRequest, pickTreatedPersona, stepLabel, type FfStepId } from "../lib/fastForward";
import { formatDuration } from "../lib/format";
import { label } from "../lib/labels";
import { recordFastForwarded } from "../lib/progressStore";
import type { Play } from "../lib/types";
import styles from "./FastForwardPanel.module.css";

type Phase = "idle" | "running" | "failed" | "measureFailed" | "done";
type StepStatus = "waiting" | "running" | "done" | "failed";

interface StepState {
  status: StepStatus;
  /** Real elapsed milliseconds for this step, once it has finished. */
  ms?: number;
}

/** The sandbox listed nobody who received the play. */
class NoTreatedPersona extends Error {}

const ORDER: readonly FfStepId[] = ["lookup", "order", "measure"];
const STATUS_WORD: Record<StepStatus, string> = { waiting: "Waiting", running: "Running", done: "Done", failed: "Failed" };

const freshSteps = (): Record<FfStepId, StepState> => ({
  lookup: { status: "waiting" },
  order: { status: "waiting" },
  measure: { status: "waiting" },
});

/** "See what measuring looks like" (E2). One click runs, in the browser and with existing calls
 * only, what a day of the pilot would: a treated customer orders through the chat order flow
 * ("add:<sku>"), then Measure joins the orders against the holdout. Everything it creates is
 * SYNTHETIC sandbox data. The steps are honest: each shows its real elapsed time, and a failure
 * says exactly how far it got. If the order was placed and Measure failed, only Run Measure is
 * offered again (the order is not placed twice). */
export function FastForwardPanel({
  play,
  done,
  onFinished,
}: {
  play: Play;
  /** The session's single-use crumb: the sequence already ran for this play. */
  done: boolean;
  /** Called after Measure succeeded, so the page can read /outcomes and the stepper again. */
  onFinished: () => void | Promise<void>;
}) {
  const [phase, setPhase] = useState<Phase>(done ? "done" : "idle");
  const [steps, setSteps] = useState<Record<FfStepId, StepState>>(freshSteps);
  const [name, setName] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [noPersona, setNoPersona] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [total, setTotal] = useState<number | null>(null);
  const [live, setLive] = useState("");
  const busy = useRef(false);
  const startedAt = useRef(0);
  const resultRef = useRef<HTMLParagraphElement>(null);
  const noteId = useId();

  // A different play: start over. (The crumb flipping to "done" at the end of a run must not wipe the
  // run's own result, so it gets its own effect and only acts on an idle panel.)
  useEffect(() => {
    setPhase(done ? "done" : "idle");
    setSteps(freshSteps());
    setError(null);
    setNoPersona(false);
    setTotal(null);
    setLive("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [play.play_id]);

  useEffect(() => {
    if (done) setPhase((p) => (p === "idle" ? "done" : p));
  }, [done]);

  useEffect(() => {
    if (phase !== "running") return;
    const id = window.setInterval(() => setElapsed(performance.now() - startedAt.current), 100);
    return () => window.clearInterval(id);
  }, [phase]);

  function patch(id: FfStepId, state: StepState) {
    setSteps((prev) => ({ ...prev, [id]: state }));
  }

  /** Runs one step, timing it for real; on failure marks it and rethrows. */
  async function timed<T>(id: FfStepId, say: string, work: () => Promise<T>): Promise<T> {
    const t = performance.now();
    patch(id, { status: "running" });
    setLive(say);
    try {
      const out = await work();
      patch(id, { status: "done", ms: performance.now() - t });
      return out;
    } catch (e) {
      patch(id, { status: "failed", ms: performance.now() - t });
      throw e;
    }
  }

  async function measureStep(who: string) {
    try {
      await timed("measure", stepLabel("measure", who), () => postMeasure());
    } catch (e) {
      setError(toApiError(e, "/measure"));
      setPhase("measureFailed");
      return;
    }
    recordFastForwarded(play.play_id);
    await onFinished();
    const ms = performance.now() - startedAt.current;
    setTotal(ms);
    setElapsed(ms);
    setPhase("done");
    setLive(`Done in ${formatDuration(ms / 1000)}. The measured row is in your result above.`);
    window.setTimeout(() => resultRef.current?.focus({ preventScroll: true }), 0);
  }

  async function run() {
    if (busy.current || phase === "done") return;
    busy.current = true;
    try {
      setError(null);
      setNoPersona(false);
      setSteps(freshSteps());
      setPhase("running");
      startedAt.current = performance.now();
      setElapsed(0);

      let who = "the customer";
      let customerId = "";
      try {
        const persona = await timed("lookup", stepLabel("lookup", who), async () => {
          const customers = await getDemoCustomers(play.play_id);
          const picked = pickTreatedPersona(customers, play.target.node_ids);
          if (!picked) throw new NoTreatedPersona();
          return picked;
        });
        who = persona.display_name;
        customerId = persona.customer_id;
        setName(who);
      } catch (e) {
        setNoPersona(e instanceof NoTreatedPersona);
        setError(toApiError(e, "/customers/demo"));
        setPhase("failed");
        return;
      }

      try {
        await timed("order", stepLabel("order", who), () =>
          sendChat(orderRequest(customerId, play.target.sku), () => {
            // The reply is the shop's confirmation; the order itself is what Measure reads.
          }),
        );
      } catch (e) {
        setError(toApiError(e, "/chat"));
        setPhase("failed");
        return;
      }

      await measureStep(who);
    } finally {
      busy.current = false;
    }
  }

  async function runMeasureOnly() {
    if (busy.current) return;
    busy.current = true;
    try {
      setError(null);
      setPhase("running");
      await measureStep(name ?? "the customer");
    } finally {
      busy.current = false;
    }
  }

  const running = phase === "running";
  const finished = phase === "done";
  const who = name ?? "the customer";
  const showSteps = phase !== "idle" && !(finished && total === null);

  return (
    <section className={`card ${styles.panel}`} aria-labelledby="ff-title" data-testid="fast-forward" data-phase={phase}>
      <div className={styles.head}>
        <h2 id="ff-title" className={styles.title}>
          {FF_TITLE}
        </h2>
        <Badge kind="synthetic" detail="sandbox data" />
      </div>
      <p className={styles.lead}>
        {finished
          ? `This ran in your sandbox: one synthetic order for ${name ?? "a treated customer"} of ${label("sku", play.target.sku)}, then Measure against the holdout. It shows the loop working. It is a demonstration, not a result.`
          : `Nothing is measured yet, and a real result needs real orders. This places one synthetic order for a treated customer of ${label("sku", play.target.sku)}, then runs Measure against the holdout, so you can see the loop close. It is a sandbox demonstration, not a result.`}
      </p>

      {phase !== "measureFailed" ? (
        <div className={styles.row}>
          <button
            type="button"
            className={styles.go}
            onClick={run}
            disabled={running || finished}
            aria-describedby={finished ? noteId : undefined}
            data-testid="fast-forward-go"
          >
            {running ? "Fast-forwarding…" : FF_BUTTON}
          </button>
          {finished ? (
            <p id={noteId} className={styles.note} data-testid="fast-forward-already">
              {FF_ALREADY}
            </p>
          ) : null}
          {running ? (
            <p className={styles.note} aria-hidden="true" data-testid="fast-forward-elapsed">
              Elapsed {formatDuration(elapsed / 1000)}
            </p>
          ) : null}
        </div>
      ) : null}

      {showSteps ? (
        <ol className={styles.steps} aria-label="Fast-forward progress" data-testid="fast-forward-steps">
          {ORDER.map((id) => (
            <li key={id} className={styles.step} data-ff-step={id} data-status={steps[id].status}>
              <span className={styles.state}>{STATUS_WORD[steps[id].status]}</span>
              <span>{stepLabel(id, who)}</span>
              {steps[id].ms !== undefined ? <span className={styles.time}>({formatDuration(steps[id].ms! / 1000)})</span> : null}
            </li>
          ))}
        </ol>
      ) : null}

      {finished && total !== null ? (
        <p ref={resultRef} tabIndex={-1} className={styles.result} data-testid="fast-forward-done">
          Done in {formatDuration(total / 1000)}. The measured row is in your result above.
        </p>
      ) : null}

      {phase === "failed" && error ? (
        noPersona ? (
          <ErrorCard
            error={error}
            compact
            onRetry={run}
            title="No treated customer to order for"
            body="The sandbox lists no customer who received this play, so nothing was ordered or measured."
          />
        ) : (
          <ErrorCard
            error={error}
            compact
            onRetry={run}
            title={steps.order.status === "failed" ? `${who}'s order did not go through` : undefined}
            body={steps.order.status === "failed" ? "Nothing was ordered and nothing was measured. Retry to start again." : undefined}
          />
        )
      ) : null}

      {phase === "measureFailed" ? (
        <>
          <ErrorCard
            error={error}
            compact
            title="Order placed. Measure failed."
            body={`${who}'s synthetic order was placed, but Measure did not run, so nothing is measured yet. Run Measure to finish; the order is not placed again.`}
          />
          <div className={styles.row}>
            <button type="button" className={styles.measureOnly} onClick={runMeasureOnly} data-testid="fast-forward-run-measure">
              Run Measure
            </button>
          </div>
        </>
      ) : null}

      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true" data-testid="fast-forward-live">
        {live}
      </div>
    </section>
  );
}
