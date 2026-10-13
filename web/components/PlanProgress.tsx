import { planSteps } from "../lib/planSteps";
import type { TraceEvent } from "../lib/types";
import { Icon } from "./icons";

/** The steps of a live plan as a compact list: a tick as each completes, and for each step what
 * produced it ("Gemini on Vertex AI" only on the drafting step of a Vertex run, otherwise
 * "deterministic, in the service" or "scripted fixture, no model call"). It reads the events the
 * stream has delivered and invents nothing. */
export function PlanProgress({ events, backend }: { events: TraceEvent[]; backend: string }) {
  const steps = planSteps(events, backend);
  return (
    <ol className="plan-progress" data-testid="plan-progress" aria-label="Planning steps">
      {steps.map((s) => (
        <li key={s.id} className="plan-progress__step" data-testid="plan-step" data-step={s.id} data-state={s.state}>
          <span className={`plan-progress__mark plan-progress__mark--${s.state}`} aria-hidden="true">
            {s.state === "done" ? <Icon name="check" size={14} /> : <span className="plan-progress__dot" />}
          </span>
          <span className="plan-progress__label">{s.label}</span>
          <span className="plan-progress__prov" data-testid="plan-step-provenance">
            {s.provenance}
          </span>
          <span className="plan-progress__state">{s.note ? `${s.state}: ${s.note}` : s.state}</span>
        </li>
      ))}
    </ol>
  );
}
