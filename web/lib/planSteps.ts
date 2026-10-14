// The compact step list on the Plan live path (components/PlanProgress.tsx). Nothing here is
// invented: each step's state comes from the trace events that have actually arrived, and each
// carries a provenance label saying what produced it. Only the drafting step can be a model call.
import type { TraceEvent } from "./types";

/** What produced a step. The words are fixed so no screen can claim more than this. */
export const PROVENANCE = {
  gemini: "Gemini on Vertex AI",
  deterministic: "deterministic, in the service",
  scripted: "scripted fixture, no model call",
  /** The offer-copy step line when the response says the copy was templated (copy.source "templated"): a
   * BigQuery attempt is made under a budget. It never says the offer was written by BigQuery or by a model.
   * Shown only through copyStepLine() in approveMachine.ts, which derives it from the response. */
  offerCopy: "templated (BigQuery attempted under a budget)",
  /** The offer-copy step line while Approve is in flight: no claim about the source, which is not known yet. */
  offerCopyPending: "Writing the offer copy; its source is shown when Approve finishes",
} as const;

export type PlanStepId = "forecast" | "draft" | "guardrails" | "accepted";
export type PlanStepState = "waiting" | "working" | "done";

export interface PlanStep {
  id: PlanStepId;
  label: string;
  provenance: string;
  state: PlanStepState;
  /** Extra words for the state, such as "2 drafts" when a guardrail sent the planner back. */
  note: string | null;
}

const hasCall = (events: TraceEvent[], name: string) => events.some((e) => e.function_call?.name === name);
const responses = (events: TraceEvent[], name: string) => events.filter((e) => e.function_response?.name === name);

/** The rule id(s) a failed check names, from check_guardrails's structured `results` ({rule, passed}) or
 * from propose_play's plain-English `errors` ("guardrail margin_floor: net margin ..."). */
export function failedRules(resp: Record<string, unknown> | undefined): string[] {
  if (!resp) return [];
  const results = Array.isArray(resp.results) ? (resp.results as Record<string, unknown>[]) : [];
  const fromResults = results.filter((r) => r.passed === false).map((r) => String(r.rule));
  const errors = Array.isArray(resp.errors) ? (resp.errors as unknown[]) : [];
  const fromErrors = errors
    .map((e) => (typeof e === "string" ? e.match(/guardrail\s+(\w+)/i)?.[1] : undefined))
    .filter((r): r is string => Boolean(r));
  return Array.from(new Set([...fromResults, ...fromErrors]));
}

const isFailure = (e: TraceEvent) =>
  (e.function_response?.name === "check_guardrails" && e.function_response.response?.all_passed === false) ||
  (e.function_response?.name === "propose_play" && e.function_response.response?.valid === false) ||
  Boolean(e.text?.toLowerCase().startsWith("guardrail failed"));

/** Why a failed check failed, from the event's own payload: the rule id(s) it names, else the first error
 * string it carries (clipped), else null. */
function reasonOf(e: TraceEvent): string | null {
  const resp = e.function_response?.response;
  const rules = failedRules(resp);
  if (rules.length) return rules.join(", ");
  const errors = Array.isArray(resp?.errors) ? (resp.errors as unknown[]).filter((x): x is string => typeof x === "string" && x.trim() !== "") : [];
  if (errors.length) return errors[0].length > 70 ? `${errors[0].slice(0, 69)}…` : errors[0];
  const m = e.text?.match(/^guardrail failed:?\s*([A-Za-z0-9_]+)/i);
  return m ? m[1] : null;
}

/** One line per rejected attempt: "Rejected: margin_floor, revising", or "Rejected, revising" when the
 * event names no reason. A failure and the failure notice that follows it with no new draft in between
 * are one rejection (the same pairing the trace panel marks as a revision). */
export function planRejections(events: TraceEvent[]): string[] {
  const out: string[] = [];
  let awaiting = false;
  for (const e of events) {
    if (isFailure(e)) {
      if (!awaiting) out.push(reasonOf(e) ?? "");
      else if (out[out.length - 1] === "") out[out.length - 1] = reasonOf(e) ?? "";
      awaiting = true;
    } else if (e.function_call?.name === "propose_play") {
      awaiting = false;
    }
  }
  return out.map((r) => (r ? `Rejected: ${r}, revising` : "Rejected, revising"));
}

/** The four lines of a live plan and where each stands, from the events seen so far: "Reading the
 * forecast", the draft ("Gemini proposing" on a Vertex run, the scripted planner otherwise), "Guardrails
 * checking" and "Plan accepted". The first of the first three that is not finished is "working"; a draft
 * a guardrail sent back puts the drafting step back to "working". A run that has ended (its run_summary
 * arrived, or `ended`) shows every step done. `backend` is the planner backend the run was accepted
 * with: only "vertex" is a model call. */
export function planSteps(events: TraceEvent[], backend: string, ended = false): PlanStep[] {
  const summary = events.some((e) => e.kind === "run_summary");
  const over = ended || summary;

  const proposeReplies = responses(events, "propose_play");
  const checkReplies = responses(events, "check_guardrails");
  const proposeCalls = events.filter((e) => e.function_call?.name === "propose_play").length;
  const proposed = proposeReplies.length;
  const accepted = proposeReplies.some((e) => e.function_response?.response?.valid === true);
  const passed = accepted || checkReplies.some((e) => e.function_response?.response?.all_passed === true);
  const rejections = planRejections(events);
  // A revision is owed (the last check failed and no new draft has been asked for) or being written.
  let awaiting = false;
  for (const e of events) {
    if (isFailure(e)) awaiting = true;
    else if (e.function_call?.name === "propose_play") awaiting = false;
  }
  const draftBusy = awaiting || proposeCalls > proposed;

  const forecastDone = responses(events, "estimate_outcomes").length > 0 || proposeCalls > 0 || checkReplies.length > 0;
  const done: Record<PlanStepId, boolean> = {
    forecast: over || forecastDone,
    draft: over || (proposed > 0 && !draftBusy),
    guardrails: over || passed,
    accepted: over || accepted,
  };
  const order: PlanStepId[] = ["forecast", "draft", "guardrails"];
  const firstOpen = order.find((id) => !done[id]);
  const stateOf = (id: PlanStepId): PlanStepState => (done[id] ? "done" : id === firstOpen ? "working" : "waiting");

  const scripted = backend !== "vertex";
  const draftProvenance = scripted ? PROVENANCE.scripted : PROVENANCE.gemini;
  const revised = rejections.length > 0;
  return [
    { id: "forecast", label: "Reading the forecast", provenance: PROVENANCE.deterministic, state: stateOf("forecast"), note: null },
    {
      id: "draft",
      label: scripted ? "Scripted planner proposing" : "Gemini proposing",
      provenance: draftProvenance,
      state: stateOf("draft"),
      note: revised ? `draft ${rejections.length + 1}` : null,
    },
    {
      id: "guardrails",
      label: "Guardrails checking",
      provenance: PROVENANCE.deterministic,
      state: stateOf("guardrails"),
      note: revised && !passed ? "revising after a failed check" : null,
    },
    { id: "accepted", label: "Plan accepted", provenance: PROVENANCE.deterministic, state: done.accepted ? "done" : "waiting", note: null },
  ];
}
