"use client";

import { useEffect, useRef, useState } from "react";
import { getEvents } from "../lib/api";
import { SourceBadge } from "./SourceBadge";
import { annotate, EventRow } from "./traceRows";
import type { EventsResponse, TraceEvent } from "../lib/types";

export function TracePanel({ runId }: { runId: string }) {
  const [response, setResponse] = useState<EventsResponse | null>(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [replaying, setReplaying] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    let cancelled = false;
    getEvents(runId).then((res) => {
      if (!cancelled) {
        setResponse(res);
        setVisibleCount(res.events.length);
      }
    });
    return () => {
      cancelled = true;
      timers.current.forEach(clearTimeout);
    };
  }, [runId]);

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

  if (!response) return <p className="muted">Loading trace…</p>;

  // The trace's own terminal run_summary record (agents/planner/run.py guarantees exactly one)
  // carries this run's recording date (a seeded recording only) and fallback reason (a rules
  // fallback only); fall back to the events response's own recorded_at when the run itself has
  // none (e.g. a trace with no run_summary at all).
  const runSummary = events.find((e) => e.kind === "run_summary");
  const rows = annotate(events).slice(0, visibleCount);

  return (
    <div className="trace-panel">
      <div className="trace-panel__header">
        <SourceBadge source={response.source} recordedAt={runSummary?.recorded_at ?? response.recorded_at} fallbackReason={runSummary?.fallback_reason} />
        <span className="trace-panel__run-id muted">run {runId}</span>
        <button type="button" onClick={replay} disabled={replaying}>
          {replaying ? "Replaying (4x)…" : "Replay at 4x"}
        </button>
      </div>
      <ol className="trace-panel__list" tabIndex={0} aria-label={`Agent trace for run ${runId}`}>
        {rows.map((row) => (
          <EventRow key={row.event.seq} row={row} />
        ))}
      </ol>
    </div>
  );
}
