// The planner's propose_play tries, paired up from a trace's raw events: what the trace panel's
// "guardrail attempts" list renders. Pure (no React) so the data shape is unit-tested on its own
// (tests/e2e/trace-attempts.spec.ts). A trace recorded before agents/planner/run.py wrote
// `attempt` / `rationale` / `rejections` still works: the number comes from the order, the
// rationale from the call's args (cut at 400 characters), the rejections from the response's
// "guardrail <rule>: <reason>" error strings.
import type { TraceEvent } from "../lib/types";

export interface Rejection {
  guardrail: string;
  reason: string;
}

export interface Attempt {
  n: number;
  /** Call seen, no response yet: a live run that is still checking this draft. */
  pending: boolean;
  accepted: boolean;
  rejections: Rejection[];
  rationale: string | null;
  /** True when only the 400-character copy from the call's args is available. */
  rationaleCut: boolean;
  offsetMs: number;
}

const CUT_AT = 400;

export function rejectionsFromErrors(errors: unknown): Rejection[] {
  if (!Array.isArray(errors)) return [];
  return errors.map((e) => {
    const text = String(e);
    const m = text.match(/^guardrail (\w+): ([\s\S]*)$/);
    return m ? { guardrail: m[1], reason: m[2] } : { guardrail: "schema", reason: text };
  });
}

function rationaleOf(call: TraceEvent): { text: string | null; cut: boolean } {
  if (call.rationale) return { text: call.rationale, cut: false };
  const play = call.function_call?.args?.play as { rationale?: unknown } | undefined;
  const shown = typeof play?.rationale === "string" ? play.rationale : null;
  return { text: shown, cut: shown !== null && shown.length >= CUT_AT && shown.endsWith("...") };
}

export function buildAttempts(events: TraceEvent[]): Attempt[] {
  const attempts: Attempt[] = [];
  let open: Attempt | null = null;
  for (const e of events) {
    if (e.function_call?.name === "propose_play") {
      const { text, cut } = rationaleOf(e);
      open = { n: e.attempt ?? attempts.length + 1, pending: true, accepted: false, rejections: [], rationale: text, rationaleCut: cut, offsetMs: e.ts_offset_ms };
      attempts.push(open);
    } else if (e.function_response?.name === "propose_play" && open) {
      const resp = e.function_response.response ?? {};
      open.pending = false;
      open.accepted = resp.valid === true;
      open.rejections = open.accepted ? [] : (e.rejections ?? rejectionsFromErrors(resp.errors));
      open.offsetMs = e.ts_offset_ms;
      open = null;
    }
  }
  return attempts;
}
