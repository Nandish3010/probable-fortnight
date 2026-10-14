"use client";

import { useEffect, useState } from "react";
import { planRejections, planSteps } from "../lib/planSteps";
import type { TraceEvent } from "../lib/types";
import { Icon } from "./icons";

/** The steps of a live plan as a compact list: "Reading the forecast", "Gemini proposing" (the scripted
 * planner on a stub backend), "Guardrails checking", and "Plan accepted" once it is. Each step carries
 * what produced it ("Gemini on Vertex AI" only on the drafting step of a Vertex run, otherwise
 * "deterministic, in the service" or "scripted fixture, no model call"). A rejected draft adds a line
 * ("Rejected: margin_floor, revising") before the accepted one. The step being worked on counts its own
 * seconds ("Gemini proposing · 12 s"), so the text changes every second and a step is never a bare
 * spinner. It reads the events the stream has delivered and invents nothing. */
export function PlanProgress({ events, backend }: { events: TraceEvent[]; backend: string }) {
  const steps = planSteps(events, backend);
  const rejections = planRejections(events);
  const active = steps.find((s) => s.state === "working") ?? null;
  // The counter restarts when the work moves to another step, or back to the draft after a rejection.
  const key = active ? `${active.id}:${rejections.length}` : null;
  const elapsed = useElapsedSeconds(key);
  const acceptedIndex = steps.findIndex((s) => s.id === "accepted");
  return (
    <ol className="plan-progress" data-testid="plan-progress" aria-label="Planning steps">
      {steps.map((s, i) => (
        <PlanLines key={s.id} before={i === acceptedIndex ? rejections : []}>
          <li className="plan-progress__step" data-testid="plan-step" data-step={s.id} data-state={s.state}>
            <span className={`plan-progress__mark plan-progress__mark--${s.state}`} aria-hidden="true">
              {s.state === "done" ? <Icon name="check" size={14} /> : <span className="plan-progress__dot" />}
            </span>
            <span className="plan-progress__label">
              {s.label}
              {s.state === "working" ? (
                <span className="plan-progress__elapsed" data-testid="plan-step-elapsed">
                  {` · ${elapsed} s`}
                </span>
              ) : null}
            </span>
            <span className="plan-progress__prov" data-testid="plan-step-provenance">
              {s.provenance}
            </span>
            <span className="plan-progress__state">{s.note ? `${s.state}: ${s.note}` : s.state}</span>
          </li>
        </PlanLines>
      ))}
    </ol>
  );
}

function PlanLines({ before, children }: { before: string[]; children: React.ReactNode }) {
  return (
    <>
      {before.map((text, i) => (
        <li key={`rej-${i}`} className="plan-progress__step plan-progress__step--rejected" data-testid="plan-rejected">
          <span className="plan-progress__mark plan-progress__mark--rejected" aria-hidden="true">
            <span className="plan-progress__dot" />
          </span>
          <span className="plan-progress__label">{text}</span>
        </li>
      ))}
      {children}
    </>
  );
}

/** Whole seconds since `key` last changed, ticking once a second; 0 while there is no key. */
function useElapsedSeconds(key: string | null): number {
  const [clock, setClock] = useState(() => ({ key, t0: Date.now(), now: Date.now() }));
  useEffect(() => {
    const t = Date.now();
    setClock({ key, t0: t, now: t });
    if (key === null) return;
    const id = setInterval(() => setClock((c) => ({ ...c, now: Date.now() })), 1000);
    return () => clearInterval(id);
  }, [key]);
  if (key === null || clock.key !== key) return 0;
  return Math.max(0, Math.floor((clock.now - clock.t0) / 1000));
}
