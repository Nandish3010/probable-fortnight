"use client";

import { useEffect, useRef, useState } from "react";
import { getEvents } from "../lib/api";
import { Badge } from "./Badge";
import type { TraceEvent } from "../lib/types";

// Short, human-scannable rendering of one value -- never the full nested structure. An array
// collapses to its length, an object to its key count; only a short scalar is shown in full.
function shortValue(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return `[${v.length} item${v.length === 1 ? "" : "s"}]`;
  if (typeof v === "object") {
    const keys = Object.keys(v as Record<string, unknown>);
    return `{${keys.length} field${keys.length === 1 ? "" : "s"}}`;
  }
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 48 ? `${s.slice(0, 45)}…` : s;
}

function summarizeResponse(event: TraceEvent): string {
  const resp = event.function_response?.response;
  if (!resp) return "";
  if (typeof resp.passed === "boolean") {
    const rule = typeof resp.rule === "string" ? ` (${resp.rule})` : "";
    const detail = typeof resp.detail === "string" ? `: ${resp.detail}` : "";
    return `passed=${resp.passed}${rule}${detail}`;
  }
  return Object.entries(resp)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${shortValue(v)}`)
    .join(", ");
}

export function TracePanel({ runId }: { runId: string }) {
  const [events, setEvents] = useState<TraceEvent[] | null>(null);
  const [visibleCount, setVisibleCount] = useState(0);
  const [replaying, setReplaying] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    let cancelled = false;
    getEvents(runId).then((res) => {
      if (!cancelled) {
        setEvents(res.events);
        setVisibleCount(res.events.length);
      }
    });
    return () => {
      cancelled = true;
      timers.current.forEach(clearTimeout);
    };
  }, [runId]);

  function replay() {
    if (!events || events.length === 0) return;
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

  if (!events) return <p className="muted">Loading trace…</p>;

  return (
    <div className="trace-panel">
      <div className="trace-panel__header">
        <Badge kind="replay" detail={`run ${runId}`} />
        <button type="button" onClick={replay} disabled={replaying}>
          {replaying ? "Replaying (4x)…" : "Replay at 4x"}
        </button>
      </div>
      <ol className="trace-panel__list" tabIndex={0} aria-label={`Agent trace for run ${runId}`}>
        {events.slice(0, visibleCount).map((event) => {
          const raw = event.function_call?.args ?? event.function_response?.response;
          return (
            <li key={event.seq} className={`trace-panel__event trace-panel__event--${event.level ?? "info"}`}>
              <span className="trace-panel__offset">+{event.ts_offset_ms}ms</span>
              <span className="trace-panel__author">{event.author}</span>
              {event.function_call ? (
                <span className="trace-panel__body">call {event.function_call.name}</span>
              ) : event.function_response ? (
                <span className="trace-panel__body">
                  {event.function_response.name} → {summarizeResponse(event)}
                </span>
              ) : (
                <span className="trace-panel__body">{event.text}</span>
              )}
              <span className="trace-panel__invocation muted">{event.invocation_id}</span>
              {raw ? (
                <details className="trace-panel__raw">
                  <summary>full JSON</summary>
                  <pre>{JSON.stringify(raw, null, 2)}</pre>
                </details>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
