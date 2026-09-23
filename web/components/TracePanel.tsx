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

// A one-line, plain-English summary of what a tool call is doing, keyed off the shape each real
// tool in agents/planner/tools.py takes. Anything not called out by name falls back to the first
// few argument keys so a new tool never renders blank.
function summarizeCall(name: string, args: Record<string, unknown> | undefined): string {
  const a = args ?? {};
  const play = (a.play ?? a.play_draft) as Record<string, unknown> | undefined;
  switch (name) {
    case "propose_play": {
      if (!play) return "draft a play";
      const mechanic = play.mechanic as string | undefined;
      const target = play.target as Record<string, unknown> | undefined;
      const units = target?.units;
      const sku = target?.sku;
      return `${mechanic ?? "play"} on ${sku ?? "target"}${units ? ` (${units} units)` : ""}`;
    }
    case "check_guardrails":
      return play ? `check the ${(play.mechanic as string) ?? "draft"} play against every guardrail` : "check guardrails";
    case "estimate_outcomes":
      return "estimate rupees recovered, response rate and margin for this draft";
    case "get_gap":
      return `read gap ${a.gap_id ?? ""}`.trim();
    case "get_candidate_audiences":
      return "look up candidate audiences for this gap";
    case "get_past_plays":
      return "look up past plays of this shape";
    default: {
      const keys = Object.keys(a).slice(0, 3);
      return keys.length ? keys.map((k) => `${k}=${shortValue(a[k])}`).join(", ") : "";
    }
  }
}

// Extract the guardrail rule id(s) a failure names, from either check_guardrails's structured
// `results` (list of {rule, passed, detail}) or propose_play's plain-English `errors` strings
// ("guardrail margin_floor: net margin 1.96% ...").
function failedRules(resp: Record<string, unknown> | undefined): string[] {
  if (!resp) return [];
  const results = Array.isArray(resp.results) ? (resp.results as Record<string, unknown>[]) : [];
  const fromResults = results.filter((r) => r.passed === false).map((r) => String(r.rule));
  const errors = Array.isArray(resp.errors) ? (resp.errors as unknown[]) : [];
  const fromErrors = errors
    .map((e) => (typeof e === "string" ? e.match(/guardrail\s+(\w+)/i)?.[1] : undefined))
    .filter((r): r is string => Boolean(r));
  return Array.from(new Set([...fromResults, ...fromErrors]));
}

function summarizeResponse(name: string, resp: Record<string, unknown> | undefined): string {
  if (!resp) return "";
  const rules = failedRules(resp);
  if (rules.length) return `failed: ${rules.join(", ")}`;
  if (typeof resp.passed === "boolean") {
    const rule = typeof resp.rule === "string" ? ` (${resp.rule})` : "";
    const detail = typeof resp.detail === "string" ? `: ${resp.detail}` : "";
    return `passed=${resp.passed}${rule}${detail}`;
  }
  if (name === "propose_play" && resp.valid === true) return `valid, play ${resp.play_id ?? ""}`.trim();
  if (name === "check_guardrails" && resp.all_passed === true) return "all guardrails passed";
  return Object.entries(resp)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${shortValue(v)}`)
    .join(", ");
}

interface Row {
  event: TraceEvent;
  isGuardrailFailure: boolean;
  isRevision: boolean;
  revisionNumber: number | null;
}

// One pass over the events: flags the guardrail check (or propose_play call) that reports a
// failure, and the very next propose_play call that follows it -- the "revision" the failure
// provoked -- so the timeline can mark that cause -> effect pair instead of leaving the judge to
// infer it from raw JSON.
function annotate(events: TraceEvent[]): Row[] {
  let revisionCount = 0;
  let awaitingRevision = false;
  return events.map((event) => {
    const respName = event.function_response?.name;
    const resp = event.function_response?.response;
    const isGuardrailFailure =
      (respName === "check_guardrails" && resp?.all_passed === false) ||
      (respName === "propose_play" && resp?.valid === false) ||
      Boolean(event.text?.toLowerCase().startsWith("guardrail failed"));
    let isRevision = false;
    let revisionNumber: number | null = null;
    if (isGuardrailFailure) {
      awaitingRevision = true;
    } else if (awaitingRevision && event.function_call?.name === "propose_play") {
      revisionCount += 1;
      isRevision = true;
      revisionNumber = revisionCount;
      awaitingRevision = false;
    }
    return { event, isGuardrailFailure, isRevision, revisionNumber };
  });
}

function EventRow({ row }: { row: Row }) {
  const { event, isGuardrailFailure, isRevision, revisionNumber } = row;
  const raw = event.function_call?.args ?? event.function_response?.response;
  return (
    <li
      className={`trace-panel__event trace-panel__event--${event.level ?? "info"}${
        isGuardrailFailure ? " trace-panel__event--guardrail-fail" : ""
      }${isRevision ? " trace-panel__event--revision" : ""}`}
    >
      <div className="trace-panel__row">
        <span className="trace-panel__offset">+{event.ts_offset_ms}ms</span>
        <span className="trace-panel__author">{event.author}</span>
        {isGuardrailFailure ? (
          <span className="trace-panel__marker trace-panel__marker--fail" title="Guardrail check failed">
            <span aria-hidden>&#9888;</span> guardrail failed
          </span>
        ) : null}
        {isRevision ? (
          <span className="trace-panel__marker trace-panel__marker--revision" title="Revised after a guardrail failure">
            <span aria-hidden>&#8635;</span> revision {revisionNumber}
          </span>
        ) : null}
      </div>
      <div className="trace-panel__body">
        {event.function_call ? (
          <>
            called <code className="trace-panel__code">{event.function_call.name}</code>
            {": "}
            {summarizeCall(event.function_call.name, event.function_call.args)}
          </>
        ) : event.function_response ? (
          <>
            <code className="trace-panel__code">{event.function_response.name}</code>
            {" → "}
            {summarizeResponse(event.function_response.name, event.function_response.response)}
          </>
        ) : (
          event.text
        )}
      </div>
      <span className="trace-panel__invocation muted">{event.invocation_id}</span>
      {raw ? (
        <details className="trace-panel__raw">
          <summary>full JSON</summary>
          <pre>{JSON.stringify(raw, null, 2)}</pre>
        </details>
      ) : null}
    </li>
  );
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

  const rows = annotate(events).slice(0, visibleCount);

  return (
    <div className="trace-panel">
      <div className="trace-panel__header">
        <Badge kind="replay" detail={`run ${runId}`} />
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
