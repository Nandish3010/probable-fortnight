"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getEvents } from "../lib/api";
import { toApiError, type ApiError } from "../lib/apiError";
import { recordedEvents } from "../lib/recorded";
import { Badge } from "./Badge";
import { Details } from "./Details";
import { ErrorCard } from "./ErrorCard";
import { traceDurationMs } from "../lib/health";
import { ModelChip } from "./ModelChip";
import { SourceBadge } from "./SourceBadge";
import { TraceView } from "./traceRows";
import type { EventsResponse, TraceEvent } from "../lib/types";

export function TracePanel({ runId }: { runId: string }) {
  const [response, setResponse] = useState<EventsResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  // True when the visitor chose "Show recorded result" after the live read failed.
  const [fromRecorded, setFromRecorded] = useState(false);
  const [visibleCount, setVisibleCount] = useState(0);
  const [replaying, setReplaying] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // The shipped recording is one run's trace; it is offered only for that run, never under another play.
  const [recordedMatches, setRecordedMatches] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    let cancelled = false;
    setResponse(null);
    setError(null);
    setFromRecorded(false);
    getEvents(runId)
      .then((res) => {
        if (!cancelled) {
          setResponse(res);
          setVisibleCount(res.events.length);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(toApiError(e, `/events/${runId}`));
      });
    return () => {
      cancelled = true;
      timers.current.forEach(clearTimeout);
    };
  }, [runId, attempt]);

  useEffect(() => {
    if (!error) return;
    let cancelled = false;
    recordedEvents().then((r) => {
      if (!cancelled) setRecordedMatches(r.run_id === runId);
    });
    return () => {
      cancelled = true;
    };
  }, [error, runId]);

  const showRecorded = useCallback(async () => {
    const res = await recordedEvents();
    setFromRecorded(true);
    setError(null);
    setResponse(res);
    setVisibleCount(res.events.length);
  }, []);

  const events: TraceEvent[] = response?.events ?? [];

  function replay() {
    if (events.length === 0) return;
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setReplaying(true);
    setVisibleCount(0);
    const REPLAY_SPEED = 4;
    events.forEach((event, idx) => {
      const t = setTimeout(() => {
        setVisibleCount(idx + 1);
        if (idx === events.length - 1) setReplaying(false);
      }, event.ts_offset_ms / REPLAY_SPEED);
      timers.current.push(t);
    });
  }

  if (error) {
    return <ErrorCard error={error} compact onRetry={() => setAttempt((n) => n + 1)} onShowRecorded={recordedMatches ? showRecorded : undefined} />;
  }
  if (!response) return <p className="muted">Loading trace…</p>;

  // The trace's own terminal run_summary record (agents/planner/run.py guarantees exactly one)
  // carries this run's recording date (a seeded recording only) and fallback reason (a rules
  // fallback only); fall back to the events response's own recorded_at when the run itself has
  // none (e.g. a trace with no run_summary at all).
  const runSummary = events.find((e) => e.kind === "run_summary");

  return (
    <div className="trace-panel">
      <div className="trace-panel__header">
        <SourceBadge source={response.source} recordedAt={runSummary?.recorded_at ?? response.recorded_at} fallbackReason={runSummary?.fallback_reason} />
        {fromRecorded ? <Badge kind="replay" detail="recorded copy, live service not answering" /> : null}
        <ModelChip latencyMs={traceDurationMs(events)} />
        <button type="button" onClick={replay} disabled={replaying}>
          {replaying ? "Replaying (4x)…" : "Replay at 4x"}
        </button>
      </div>
      <TraceView events={events.slice(0, visibleCount)} label={`Agent trace for run ${runId}`} tabIndex={0} />
      <Details summary="Show technical details" testId="trace-technical-details">
        <p className="trace-panel__run-id muted" data-testid="trace-run-id">
          Run {runId}
        </p>
      </Details>
    </div>
  );
}
