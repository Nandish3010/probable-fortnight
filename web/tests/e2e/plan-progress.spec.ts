import { test, expect } from "@playwright/test";
import { approveSettled } from "./helpers";
import { PROVENANCE, planSteps } from "../../lib/planSteps";
import type { TraceEvent } from "../../lib/types";

// The step list on the Plan live path (lib/planSteps.ts, components/PlanProgress.tsx): states come
// from the events that arrived, provenance names what produced each step, and only the drafting step
// of a Vertex run says Gemini.

let seq = 0;
const ev = (over: Partial<TraceEvent>): TraceEvent => ({
  seq: seq++,
  run_id: "r",
  invocation_id: "i",
  author: "planner",
  timestamp: "2026-09-12T03:30:00Z",
  ts_offset_ms: 0,
  ...over,
});
const call = (name: string) => ev({ function_call: { name } });
const reply = (name: string, response: Record<string, unknown>) => ev({ function_response: { name, response } });
const states = (events: TraceEvent[], backend = "stub") => planSteps(events, backend).map((s) => s.state);

test.describe("planSteps", () => {
  test("no events yet: the first step is working, the rest wait", () => {
    expect(states([])).toEqual(["working", "waiting", "waiting", "waiting"]);
  });

  test("each step ticks as its evidence arrives", () => {
    const governor = ev({ author: "cost_governor", text: "rupees at stake 35020 >= threshold 500" });
    expect(states([governor])).toEqual(["done", "working", "waiting", "waiting"]);
    const estimated = [governor, call("estimate_outcomes"), reply("estimate_outcomes", { result: [] })];
    expect(states(estimated)).toEqual(["done", "done", "working", "waiting"]);
    const drafted = [...estimated, call("propose_play"), reply("propose_play", { valid: false, errors: ["guardrail margin_floor"] })];
    expect(states(drafted)).toEqual(["done", "done", "done", "working"]);
    const revised = [...drafted, call("propose_play"), reply("propose_play", { valid: true, errors: [] })];
    expect(states(revised)).toEqual(["done", "done", "done", "done"]);
  });

  test("a failed guardrail check is shown as a revision, not as done", () => {
    const steps = planSteps(
      [call("propose_play"), reply("propose_play", { valid: false }), call("propose_play"), reply("propose_play", { valid: false })],
      "stub",
    );
    const guard = steps.find((s) => s.id === "guardrails")!;
    expect(guard.state).not.toBe("done");
    expect(guard.note).toMatch(/revising/);
    expect(steps.find((s) => s.id === "draft")!.note).toBe("2 drafts");
  });

  test("a finished run (run_summary) shows every step done", () => {
    expect(states([ev({ kind: "run_summary" })])).toEqual(["done", "done", "done", "done"]);
  });

  test("provenance: Gemini on Vertex AI only for the drafting step of a vertex run", () => {
    const vertex = planSteps([], "vertex");
    expect(vertex.filter((s) => s.provenance === PROVENANCE.gemini).map((s) => s.id)).toEqual(["draft"]);
    const stub = planSteps([], "stub");
    expect(stub.some((s) => /gemini/i.test(s.provenance))).toBe(false);
    expect(stub.find((s) => s.id === "draft")!.provenance).toBe("scripted fixture, no model call");
    for (const s of [...vertex, ...stub].filter((x) => x.id !== "draft")) expect(s.provenance).toBe("deterministic, in the service");
  });

  test("the offer-copy provenance never says BigQuery or a model wrote the offer", () => {
    expect(PROVENANCE.offerCopy).toBe("templated (BigQuery attempted under a budget)");
    expect(PROVENANCE.offerCopy).not.toMatch(/AI\.GENERATE|generated|written by/i);
  });
});

test.describe("Plan live: the step list streams", () => {
  test("it shows four steps with provenance, and ticks them as the run streams", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("plan-live").click();
    const progress = card.getByTestId("plan-progress");
    await expect(progress).toBeVisible();
    await expect(progress.getByTestId("plan-step")).toHaveCount(4);
    await expect(progress.getByTestId("plan-step").first()).toContainText("Check the rupees at stake");
    await expect(progress.getByTestId("plan-step").nth(2).getByTestId("plan-step-provenance")).toHaveText("scripted fixture, no model call");
    await expect(progress.getByTestId("plan-step").nth(1).getByTestId("plan-step-provenance")).toHaveText("deterministic, in the service");
    // the mock run streams for a couple of seconds: at least one step ticks while it is still going
    await expect(progress.locator('[data-testid="plan-step"][data-state="done"]').first()).toBeVisible();
    await expect(progress.getByText(/Gemini/)).toHaveCount(0); // the mock run is the stub backend
  });
});

test.describe("Approve: step provenance", () => {
  test("the three steps say what produced them; the copy step names no source until the response does, and never credits BigQuery with writing the offer", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByTestId("beat-panel").getByRole("button", { name: "Approve" }).click();
    const steps = page.getByTestId("approve-step");
    await expect(steps).toHaveCount(3);
    await approveSettled(page);
    // mocks/approve.json carries no copy field, so the response names no source: no claim at all on step 1.
    await expect(steps.nth(0).getByTestId("step-provenance")).toHaveCount(0);
    await expect(steps.nth(1).getByTestId("step-provenance")).toHaveText("deterministic, in the service");
    await expect(steps.nth(2).getByTestId("step-provenance")).toHaveText("deterministic, in the service");
  });
});

test.describe("assumption and measured labels", () => {
  test("the decision card figure says assumption, and the Approve result shows counts and no measured label", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const beat = page.getByTestId("beat-panel");
    await expect(beat.getByTestId("recovered-figure").getByTestId("basis-assumption")).toBeVisible();
    await beat.getByRole("button", { name: "Approve" }).click();
    const result = page.getByTestId("approve-result");
    await expect(result).toBeVisible({ timeout: 30_000 });
    await expect(result.getByTestId("audience-chain")).toHaveText("394 consented: 355 treated and 39 holdout");
    await expect(result.getByTestId("basis-assumption")).toBeVisible();
    await expect(result.getByTestId("basis-measured")).toHaveCount(0);
    await expect(result).not.toContainText(/response-rate difference|95% CI/i); // no measured lift before Measure
  });

  test("Outcomes labels the portfolio numbers assumption and a measured result measured", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByTestId("portfolio-card").getByTestId("basis-assumption")).toHaveCount(2);
    await expect(page.getByTestId("outcome-summary").getByTestId("basis-measured")).toHaveCount(0); // nothing measured yet
  });
});
