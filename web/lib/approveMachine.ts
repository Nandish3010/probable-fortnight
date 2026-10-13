// The state machine behind the Approve panel (design_spec.md 6.1), as a pure reducer so a node
// test can walk every transition. T0 is the moment the /approve response is received.
//
//   idle -> submitting -> animating -> settled
//                      \-> error -> submitting (Retry)
//                      \-> alreadyApproved (a 409, or a play the API already reports as approved)
//
// Step ticks, the collapse of the step list, the reveal of the result body, the delta chip and the
// final settle are reducer actions fired on a timeline by the panel; nothing here reads a clock.
import type { ApiError } from "./apiError";
import { PROVENANCE } from "./planSteps";
import type { ApproveResponse } from "./types";

export type ApprovePhase = "idle" | "submitting" | "animating" | "settled" | "error" | "alreadyApproved";

export const APPROVE_STEPS = ["Writing the offer", "Re-forecasting with the play", "Assigning the holdout"] as const;

export interface ApproveState {
  phase: ApprovePhase;
  /** The API's answer; null when a 409 or an already-approved play gives none. */
  result: ApproveResponse | null;
  error: ApiError | null;
  /** Click to response, in milliseconds. */
  elapsedMs: number | null;
  /** When the API says the play was approved (ISO string), if it does. */
  approvedAt: string | null;
  /** True when the sequence plays; false = everything renders at once (reduced motion, recorded). */
  animate: boolean;
  /** How many of the three step labels show a tick (0 to 3). */
  stepsTicked: number;
  /** The step list has collapsed to its one-line summary. */
  collapsed: boolean;
  /** The result body (heading, figure, chart, preview) is mounted. */
  bodyShown: boolean;
  /** The delta chip and the toast are visible. */
  chipShown: boolean;
}

export type ApproveAction =
  | { type: "submit" }
  | { type: "respond"; result: ApproveResponse; elapsedMs: number; reduced: boolean }
  | { type: "fail"; error: ApiError; elapsedMs?: number }
  | { type: "tick" }
  | { type: "collapse" }
  | { type: "reveal" }
  | { type: "chip" }
  | { type: "settle" };

/** Timeline in ms after T0 (design_spec.md 6.2). The stagger between step ticks is 120 ms. The
 * result body mounts once the step list has finished folding (it starts at 360 and takes 240 ms):
 * spec has it at 400, but then the heading would slide up 100 px while the list folds, which is
 * the jump the sequence must not have. Everything after it moves back by the same 200 ms. */
export const TIMELINE = {
  tickEvery: 120,
  collapse: 360,
  reveal: 600,
  chip: 1500,
  settle: 1900,
} as const;

export function initialApproveState(opts?: { alreadyApproved?: boolean; approvedAt?: string | null }): ApproveState {
  if (opts?.alreadyApproved) return alreadyApprovedState(null, opts.approvedAt ?? null);
  return {
    phase: "idle",
    result: null,
    error: null,
    elapsedMs: null,
    approvedAt: null,
    animate: true,
    stepsTicked: 0,
    collapsed: false,
    bodyShown: false,
    chipShown: false,
  };
}

function alreadyApprovedState(result: ApproveResponse | null, approvedAt: string | null): ApproveState {
  return {
    phase: "alreadyApproved",
    result,
    error: null,
    elapsedMs: null,
    approvedAt,
    animate: false,
    stepsTicked: 3,
    collapsed: true,
    bodyShown: true,
    chipShown: true,
  };
}

export function approveReducer(state: ApproveState, action: ApproveAction): ApproveState {
  switch (action.type) {
    case "submit":
      // Only from idle, or from error (Retry). Settled and already-approved are terminal.
      if (state.phase !== "idle" && state.phase !== "error") return state;
      return { ...initialApproveState(), phase: "submitting" };

    case "respond": {
      if (state.phase !== "submitting") return state;
      const approvedAt = action.result.approved_at ?? null;
      if (action.reduced) {
        return {
          ...state,
          phase: "settled",
          result: action.result,
          error: null,
          elapsedMs: action.elapsedMs,
          approvedAt,
          animate: false,
          stepsTicked: 3,
          collapsed: true,
          bodyShown: true,
          chipShown: true,
        };
      }
      return { ...state, phase: "animating", result: action.result, error: null, elapsedMs: action.elapsedMs, approvedAt };
    }

    case "fail":
      if (state.phase !== "submitting") return state;
      // A 409 means it is already approved in this session: show the recorded result, no animation.
      if (action.error.kind === "conflict") return alreadyApprovedState(null, null);
      return { ...state, phase: "error", error: action.error, elapsedMs: action.elapsedMs ?? null };

    case "tick":
      if (state.phase !== "animating") return state;
      return { ...state, stepsTicked: Math.min(3, state.stepsTicked + 1) };

    case "collapse":
      if (state.phase !== "animating") return state;
      return { ...state, stepsTicked: 3, collapsed: true };

    case "reveal":
      if (state.phase !== "animating") return state;
      return { ...state, bodyShown: true };

    case "chip":
      if (state.phase !== "animating") return state;
      return { ...state, chipShown: true };

    case "settle":
      if (state.phase !== "animating") return state;
      return { ...state, phase: "settled", stepsTicked: 3, collapsed: true, bodyShown: true, chipShown: true };

    default:
      return state;
  }
}

/** "Done in 11.8 s" from a duration in ms. */
export function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}

/** The two lines under the steps while waiting. Whole seconds, from a performance.now() delta. */
export function workingCopy(seconds: number): string {
  if (seconds >= 20) return `Still working: ${seconds} s. Taal gives up at 60 s and keeps your plan unchanged.`;
  return `Working: ${seconds} s. This takes a few seconds.`;
}

/** "HH:MM" in the tenant's time zone (all Taal timestamps are IST); null when not a timestamp. */
export function clockTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }).format(d);
}

/** What the response says about where the offer copy came from, in the two places it is shown: `badge`
 * is the chip on the result ("Copy: ..."), `step` is the provenance line on the "Writing the offer" step.
 * Both come from this one function, from `copy.source` and `copy.provenance` of POST /approve and nothing
 * else, so the two can never disagree. "bigquery" is Gemini via BigQuery. "existing" is copy stored with
 * the play: with provenance "bigquery_pregenerated" it is Gemini via BigQuery (pre-generated), otherwise
 * "stored with the play". "templated" is the template (the step line adds that BigQuery was attempted under
 * a budget; this is the only case where it says so). An absent or empty source, a source that is not a
 * string, and a source this code has not seen all give null: no badge, no step line, and never a BigQuery
 * or template claim the field does not make. Never inferred from timing or from any other field. */
export function copySourceParts(
  copy: { source?: unknown; provenance?: unknown } | null | undefined,
): { badge: string; step: string } | null {
  const source = copy?.source;
  if (typeof source !== "string" || source === "") return null;
  switch (source) {
    case "bigquery":
      return { badge: "Copy: Gemini via BigQuery", step: "Gemini via BigQuery" };
    case "existing":
      return copy?.provenance === "bigquery_pregenerated"
        ? { badge: "Copy: Gemini via BigQuery (pre-generated)", step: "Gemini via BigQuery (pre-generated)" }
        : { badge: "Copy: stored with the play", step: "stored with the play" };
    case "templated":
      return { badge: "Copy: template", step: PROVENANCE.offerCopy };
    default:
      return null;
  }
}

/** The badge next to the offer copy on the Approve result, or null when the response names no known source. */
export function copySourceLabel(copy: { source?: unknown; provenance?: unknown } | null | undefined): string | null {
  return copySourceParts(copy)?.badge ?? null;
}

/** The provenance line on the "Writing the offer" step once the response has arrived (see copySourceParts). */
export function copyStepLine(copy: { source?: unknown; provenance?: unknown } | null | undefined): string | null {
  return copySourceParts(copy)?.step ?? null;
}
