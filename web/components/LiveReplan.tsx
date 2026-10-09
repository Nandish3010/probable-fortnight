"use client";

import { useEffect, useRef, useState } from "react";
import { getRerunStatus, streamRerun } from "../lib/api";
import { TraceView } from "./traceRows";
import type { RerunAccepted, RerunResult, TraceEvent } from "../lib/types";

// If the SSE stream itself fails (dropped connection, proxy timeout, ...), fall back to polling
// GET /rerun/{run_id} (services/api/main.py) until the run finishes or this much time past the
// planner's own deadline has passed -- generous enough that a slow-to-flush "done" write is never
// mistaken for a run that hung.
const STATUS_POLL_MS = 2000;
const POLL_GRACE_MS = 30_000;

export function LiveReplan({ accepted, onDone }: { accepted: RerunAccepted; onDone: (result: RerunResult) => void }) {
  const [records, setRecords] = useState<TraceEvent[]>([]);
  const [elapsedS, setElapsedS] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  // The run starts below the recorded trace, often off screen: bring it into view once.
  useEffect(() => {
    root.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, []);

  useEffect(() => {
    // Locals, not refs: each effect invocation gets its own `finished`/`controller`, so a stray
    // callback from a run this same effect already tore down (React StrictMode's dev-only
    // mount -> cleanup -> mount, which this component must survive since `make web-test` and
    // `make live-test` both run against `next dev`) can tell it belongs to a superseded run and
    // no-op, rather than appending into the NEW run's state.
    let finished = false;
    const controller = new AbortController();
    setRecords([]);
    setElapsedS(0);
    setError(null);
    const startedAt = Date.now();
    const tick = setInterval(() => {
      if (!controller.signal.aborted) setElapsedS(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);

    async function pollStatus() {
      const deadlineMs = accepted.deadline_s * 1000 + POLL_GRACE_MS;
      while (!finished && !controller.signal.aborted && Date.now() - startedAt < deadlineMs) {
        await new Promise((resolve) => setTimeout(resolve, STATUS_POLL_MS));
        if (finished || controller.signal.aborted) return;
        try {
          const status = await getRerunStatus(accepted.run_id);
          if (status.status === "done" && status.result) {
            finished = true;
            onDone(status.result);
            return;
          }
          if (status.status === "error") {
            finished = true;
            setError(status.result?.error || "The re-plan failed.");
            return;
          }
        } catch {
          // A transient failure while polling; keep trying until the deadline above.
        }
      }
      if (!finished && !controller.signal.aborted) {
        finished = true;
        setError("The re-plan did not finish in time.");
      }
    }

    streamRerun(
      accepted.run_id,
      (record) => {
        if (controller.signal.aborted) return;
        setRecords((prev) => [...prev, record]);
      },
      controller.signal,
    )
      .then((result) => {
        if (controller.signal.aborted || finished) return;
        finished = true;
        onDone(result);
      })
      .catch(() => {
        if (controller.signal.aborted || finished) return;
        pollStatus();
      });

    return () => {
      finished = true;
      controller.abort();
      clearInterval(tick);
    };
    // Only `run_id` identifies a genuinely new run; deadline_s/backend are fixed for its lifetime
    // and onDone is called through this closure regardless of the parent's render identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accepted.run_id]);

  const headerLine =
    accepted.backend === "vertex"
      ? // eval/raw/planner_prompt_v6_2026-09-24/summary.json's real (non-fallback) Gemini runs
        // took 23,952-43,295ms end to end -- "20-40 s" rounds that range for a judge-facing line.
        "Gemini is planning — typically 20–40 s"
      : "Scripted planner is running (stub backend)";

  return (
    <div className="live-replan" data-testid="live-replan" ref={root}>
      <p className="live-replan__status">{headerLine}</p>
      <p className="muted live-replan__timing">
        {elapsedS} s elapsed · falls back to rules after {Math.round(accepted.deadline_s)} s
      </p>
      <TraceView events={records} label="Live re-plan trace" />
      {error ? (
        <p className="error" data-testid="live-replan-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
