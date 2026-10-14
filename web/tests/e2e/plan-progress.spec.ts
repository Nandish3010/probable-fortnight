import { test, expect } from "@playwright/test";
import { approveSettled, setMockDelay } from "./helpers";
import { PROVENANCE, planRejections, planSteps } from "../../lib/planSteps";
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

  test("the lines read in order: forecast, proposing, guardrails, accepted", () => {
    expect(planSteps([], "vertex").map((s) => s.label)).toEqual(["Reading the forecast", "Gemini proposing", "Guardrails checking", "Plan accepted"]);
    expect(planSteps([], "stub").map((s) => s.label)).toEqual(["Reading the forecast", "Scripted planner proposing", "Guardrails checking", "Plan accepted"]);
  });

  test("a stub backend never reads as Gemini, on any line or provenance", () => {
    for (const events of [[], [call("propose_play")], [ev({ kind: "run_summary" })]]) {
      for (const s of planSteps(events, "stub")) expect(`${s.label} ${s.provenance} ${s.note ?? ""}`).not.toMatch(/gemini/i);
    }
  });

  test("each step ticks as its evidence arrives", () => {
    const governor = ev({ author: "cost_governor", text: "rupees at stake 35020 >= threshold 500" });
    expect(states([governor])).toEqual(["working", "waiting", "waiting", "waiting"]);
    const estimated = [governor, call("estimate_outcomes"), reply("estimate_outcomes", { result: [] })];
    expect(states(estimated)).toEqual(["done", "working", "waiting", "waiting"]);
    const asked = [...estimated, call("propose_play")];
    expect(states(asked)).toEqual(["done", "working", "waiting", "waiting"]);
    const accepted = [...asked, reply("propose_play", { valid: true, errors: [] })];
    expect(states(accepted)).toEqual(["done", "done", "done", "done"]);
  });

  test("a rejected draft puts the drafting step back to working and adds one rejection line", () => {
    const rejected = [
      reply("estimate_outcomes", { result: [] }),
      call("propose_play"),
      reply("propose_play", { valid: false, errors: ["guardrail margin_floor: net margin 1.96% below the floor"] }),
      ev({ text: "Guardrail failed: margin_floor: net margin 1.96%" }),
    ];
    expect(states(rejected)).toEqual(["done", "working", "waiting", "waiting"]);
    expect(planRejections(rejected)).toEqual(["Rejected: margin_floor, revising"]);
    const steps = planSteps(rejected, "stub");
    expect(steps.find((s) => s.id === "draft")!.note).toBe("draft 2");
    expect(steps.find((s) => s.id === "guardrails")!.note).toMatch(/revising/);
    const revised = [...rejected, call("propose_play"), reply("propose_play", { valid: true, errors: [] })];
    expect(states(revised)).toEqual(["done", "done", "done", "done"]);
    expect(planRejections(revised)).toHaveLength(1);
  });

  test("the rejection reason comes from the event; with none, the line says Rejected, revising", () => {
    expect(planRejections([reply("check_guardrails", { all_passed: false, results: [{ rule: "frequency_cap", passed: false }, { rule: "margin_floor", passed: true }] })])).toEqual([
      "Rejected: frequency_cap, revising",
    ]);
    expect(planRejections([reply("propose_play", { valid: false, errors: ["$: 'play_id' is a required property"] })])).toEqual(["Rejected: $: 'play_id' is a required property, revising"]);
    expect(planRejections([reply("propose_play", { valid: false })])).toEqual(["Rejected, revising"]);
    // two failed drafts, two lines
    expect(
      planRejections([
        reply("propose_play", { valid: false, errors: ["guardrail margin_floor: x"] }),
        call("propose_play"),
        reply("propose_play", { valid: false, errors: ["guardrail cite_or_drop: y"] }),
      ]),
    ).toEqual(["Rejected: margin_floor, revising", "Rejected: cite_or_drop, revising"]);
    expect(planRejections([call("propose_play"), reply("propose_play", { valid: true })])).toEqual([]);
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
  async function startPlanLive(page: import("@playwright/test").Page) {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("plan-live").click();
    return card.getByTestId("plan-progress");
  }

  test("it shows four steps with provenance, ticks them as the run streams, and lists the rejection before the accepted line", async ({ page }) => {
    const progress = await startPlanLive(page);
    await expect(progress).toBeVisible();
    const steps = progress.getByTestId("plan-step");
    await expect(steps).toHaveCount(4);
    await expect(steps.first()).toContainText("Reading the forecast");
    await expect(steps.nth(1)).toContainText("Scripted planner proposing"); // the mock run is the stub backend
    await expect(steps.nth(2)).toContainText("Guardrails checking");
    await expect(steps.nth(3)).toContainText("Plan accepted");
    await expect(steps.nth(1).getByTestId("plan-step-provenance")).toHaveText("scripted fixture, no model call");
    await expect(steps.nth(0).getByTestId("plan-step-provenance")).toHaveText("deterministic, in the service");
    // the mock run streams for a couple of seconds: at least one step ticks while it is still going
    await expect(progress.locator('[data-testid="plan-step"][data-state="done"]').first()).toBeVisible();
    await expect(progress.getByText(/Gemini/)).toHaveCount(0);
    // the recorded mock run has one rejected draft (margin_floor); its line sits just before "Plan accepted"
    await expect(progress.getByTestId("plan-rejected")).toHaveText("Rejected: margin_floor, revising");
    const labels = await progress.locator("li").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.testid));
    expect(labels).toEqual(["plan-step", "plan-step", "plan-step", "plan-rejected", "plan-step"]);
    // and the run ends with every line done
    await expect(progress.locator('[data-testid="plan-step"][data-state="done"]')).toHaveCount(4, { timeout: 30_000 });
    await expect(progress.getByTestId("plan-step-elapsed")).toHaveCount(0);
  });

  test("the active step counts its own seconds: its text changes at least every 5 s and is never a bare spinner", async ({ page }) => {
    await setMockDelay(page, { "/events": 7000 });
    const progress = await startPlanLive(page);
    const active = progress.locator('[data-testid="plan-step"][data-state="working"]');
    await expect(active).toHaveCount(1);
    await expect(active).toContainText("Reading the forecast");
    await expect(active.getByTestId("plan-step-elapsed")).toHaveText(/^ · \d+ s$/); // from the first frame
    const seen = new Set<string>();
    const until = Date.now() + 5500;
    while (Date.now() < until) {
      seen.add(await active.getByTestId("plan-step-elapsed").innerText());
      await page.waitForTimeout(250);
    }
    expect(seen.size).toBeGreaterThanOrEqual(4); // 0 s .. 5 s: one change a second
    await expect(active.getByTestId("plan-step-elapsed")).toHaveText(/ · [4-9] s/);
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
    await expect(beat.getByTestId("recovered-figure").getByTestId("basis-projected")).toBeVisible();
    await beat.getByRole("button", { name: "Approve" }).click();
    const result = page.getByTestId("approve-result");
    await expect(result).toBeVisible({ timeout: 30_000 });
    await expect(result.getByTestId("audience-chain")).toHaveText("Reached 355 customers, 39 held back; the lift is measured once orders arrive");
    await expect(result.getByTestId("basis-projected")).toBeVisible();
    await expect(result.getByTestId("basis-measured")).toHaveCount(0);
    await expect(result).not.toContainText(/response-rate difference|95% CI/i); // no measured lift before Measure
  });

  test("Outcomes labels the portfolio numbers assumption and a measured result measured", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByTestId("portfolio-card").getByTestId("basis-projected")).toHaveCount(1); // expected recovered
    await expect(page.getByTestId("portfolio-card").getByTestId("basis-synthetic")).toHaveCount(1); // total at stake
    await expect(page.getByTestId("outcome-summary").getByTestId("basis-measured")).toHaveCount(0); // nothing measured yet
  });
});
