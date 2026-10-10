// Mock-mode fixtures (web/mocks/*.json), loaded on demand. Every import() sits inside a condition
// that is spelled `process.env.NEXT_PUBLIC_TAAL_MOCK === "1"` on purpose: Next replaces that
// expression with a literal at build time, webpack then drops the whole branch when it is false,
// and no fixture reaches the production bundle (about 170 KB of JSON before this). A helper such
// as isMockMode() would not do: the bundler only folds a condition written inline.

import type { ApproveResponse } from "./types";

export type MockKey =
  | "health" | "gaps" | "plays" | "approve" | "events" | "policy" | "rerun" | "rerun_events"
  | "capture" | "capture_lowconf" | "execution" | "outcomes" | "prior_update" | "customers_demo"
  | "chat" | "feedback_form" | "feedback_summary";

export async function mockJson(key: MockKey): Promise<unknown> {
  if (process.env.NEXT_PUBLIC_TAAL_MOCK === "1") {
    switch (key) {
      case "health": return (await import("../mocks/health.json")).default;
      case "gaps": return (await import("../mocks/gaps.json")).default;
      case "plays": return (await import("../mocks/plays.json")).default;
      case "approve": return (await import("../mocks/approve.json")).default;
      case "events": return (await import("../mocks/events.json")).default;
      case "policy": return (await import("../mocks/policy.json")).default;
      case "rerun": return (await import("../mocks/rerun.json")).default;
      case "rerun_events": return (await import("../mocks/rerun_events.json")).default;
      case "capture": return (await import("../mocks/capture.json")).default;
      case "capture_lowconf": return (await import("../mocks/capture_lowconf.json")).default;
      case "execution": return (await import("../mocks/execution.json")).default;
      case "outcomes": return (await import("../mocks/outcomes.json")).default;
      case "prior_update": return (await import("../mocks/prior_update.json")).default;
      case "customers_demo": return (await import("../mocks/customers_demo.json")).default;
      case "chat": return (await import("../mocks/chat.json")).default;
      case "feedback_form": return (await import("../mocks/feedback_form.json")).default;
      // The summary a zero-response store produces (summarize([]) output): mock mode never shows
      // simulated feedback numbers, not even to a demo viewer.
      case "feedback_summary": return (await import("../mocks/feedback_summary.json")).default;
    }
  }
  throw new Error(`mock fixture "${key}" requested outside mock mode`);
}

// Per-play overrides for the approve fixture. mocks/approve.json still holds the old Masala Chips
// stub (287 treated, 26 held back); the hero play is Tea, so a mock Approve for a play listed here
// answers with that play's own numbers: 323 consented, 291 treated, 32 held back, write-off 35,186
// to 28,659. Everything else (the forecast series, run id shape) comes from the fixture. The real
// service regenerates the fixture from the flagship; until then this keeps mock mode self-consistent.
const APPROVE_OVERRIDES: Record<string, { treated_n: number; holdout_n: number; eligible_n: number; excluded_subscribers: number; writeoff_before_inr: number; writeoff_after_inr: number }> = {
  play_tea_ds04_v1: {
    treated_n: 291,
    holdout_n: 32,
    eligible_n: 323,
    excluded_subscribers: 0,
    writeoff_before_inr: 35186,
    writeoff_after_inr: 28659,
  },
};

export async function mockApproveFor(playId: string): Promise<ApproveResponse> {
  const base = (await mockJson("approve")) as unknown as ApproveResponse;
  const o = APPROVE_OVERRIDES[playId];
  if (!o) return { ...base, play_id: playId };
  return {
    ...base,
    play_id: playId,
    assignment: {
      ...base.assignment,
      treated_n: o.treated_n,
      holdout_n: o.holdout_n,
      eligible_n: o.eligible_n,
      excluded_subscribers: o.excluded_subscribers,
      seed: `seed-${playId}`,
    },
    forecast: {
      ...base.forecast,
      run_id: `refc_${playId}_033000`,
      writeoff_before_inr: o.writeoff_before_inr,
      writeoff_after_inr: o.writeoff_after_inr,
    },
  };
}
