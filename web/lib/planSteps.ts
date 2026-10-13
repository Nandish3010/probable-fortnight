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

export type PlanStepId = "cost" | "estimate" | "draft" | "guardrails";
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

/** The four steps of a live plan and where each stands, from the events seen so far. The first step
 * that is not finished is "working" while the run is on; the ones after it are "waiting". A run that
 * has ended (its run_summary arrived, or `ended`) shows every step done. `backend` is the planner
 * backend the run was accepted with: only "vertex" is a model call. */
export function planSteps(events: TraceEvent[], backend: string, ended = false): PlanStep[] {
  const summary = events.some((e) => e.kind === "run_summary");
  const over = ended || summary;

  const proposeReplies = responses(events, "propose_play");
  const checkReplies = responses(events, "check_guardrails");
  const proposed = proposeReplies.length;
  const passed =
    proposeReplies.some((e) => e.function_response?.response?.valid === true) ||
    checkReplies.some((e) => e.function_response?.response?.all_passed === true);

  const costDone = events.some((e) => e.author === "cost_governor") || events.some((e) => e.author === "planner");
  const estimateDone = responses(events, "estimate_outcomes").length > 0 || proposed > 0;
  const draftDone = proposed > 0 || checkReplies.length > 0;
  const guardDone = passed;

  const done: Record<PlanStepId, boolean> = {
    cost: over || costDone,
    estimate: over || estimateDone,
    draft: over || draftDone,
    guardrails: over || guardDone,
  };
  const order: PlanStepId[] = ["cost", "estimate", "draft", "guardrails"];
  const firstOpen = order.find((id) => !done[id]);
  const stateOf = (id: PlanStepId): PlanStepState => (done[id] ? "done" : id === firstOpen ? "working" : "waiting");

  const draftProvenance = backend === "vertex" ? PROVENANCE.gemini : PROVENANCE.scripted;
  const drafts = proposed + (proposed === 0 && hasCall(events, "propose_play") ? 1 : 0);
  const revised = proposed > 1;
  return [
    { id: "cost", label: "Check the rupees at stake", provenance: PROVENANCE.deterministic, state: stateOf("cost"), note: null },
    { id: "estimate", label: "Estimate outcomes", provenance: PROVENANCE.deterministic, state: stateOf("estimate"), note: null },
    {
      id: "draft",
      label: "Draft the play",
      provenance: draftProvenance,
      state: stateOf("draft"),
      note: revised ? `${proposed} drafts` : drafts === 1 && !done.draft ? "drafting" : null,
    },
    {
      id: "guardrails",
      label: "Check the guardrails",
      provenance: PROVENANCE.deterministic,
      state: stateOf("guardrails"),
      note: revised && !guardDone ? "revising after a failed check" : null,
    },
  ];
}
