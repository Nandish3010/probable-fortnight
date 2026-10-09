import { test, expect } from "@playwright/test";

// Mock mode: no committed real-Gemini recording exists (harness/recorded_traces.py), so every
// seeded play -- the flagship (gap_chips_ds07) included -- has source "scripted_stub", and the
// re-plan flow below is served from web/mocks/rerun.json + rerun_events.json.
test.describe("Play Desk: provenance badges and the live re-plan flow", () => {
  test("flagship trace shows Scripted fixture; policy change streams a live re-plan to a result", async ({ page }) => {
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();

    const card = page.getByTestId("play-detail");
    const trace = card.locator(".trace-panel");
    await expect(trace.getByText("Scripted fixture")).toBeVisible();

    const liveReplan = page.getByTestId("live-replan");
    await expect(liveReplan).not.toBeVisible();

    await card.getByRole("button", { name: /Change policy/ }).click();

    // The live-replan panel appears immediately with its stub-backend header line and a ticking
    // elapsed counter, then streamed trace rows arrive one at a time (mocks/rerun_events.json's
    // frames, ~250ms apart -- see api.ts's streamRerun mock).
    await expect(liveReplan).toBeVisible();
    await expect(liveReplan.getByText("Scripted planner is running")).toBeVisible();
    await expect(liveReplan.getByText(/\d+ s elapsed/)).toBeVisible();
    await expect(liveReplan.locator(".trace-panel__event").first()).toBeVisible({ timeout: 5_000 });

    // Once the stream's terminal "done" frame lands, the result section replaces the live panel.
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    await expect(liveReplan).not.toBeVisible();
    const resultSection = card.locator(".play-card__section").filter({ hasText: "Re-plan result" });
    await expect(resultSection.getByText("Scripted fixture")).toBeVisible();
  });

  test("trace panel lists every propose_play attempt: the rejection with its guardrail, reason and rationale, then the pass", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const attempts = page.getByTestId("play-detail").locator(".trace-panel").getByTestId("trace-attempts");
    await expect(attempts).toBeVisible();

    const first = attempts.getByTestId("trace-attempt-1");
    await expect(first.locator(".trace-panel__marker--fail")).toContainText("rejected");
    await expect(first.locator("code")).toHaveText("margin_floor");
    await expect(first.getByText(/net margin 1\.96%/)).toBeVisible();
    const rejected = first.locator("details");
    await expect(rejected).not.toHaveAttribute("open", "");
    await rejected.locator("summary").click();
    await expect(rejected.getByText(/Masala Chips 200G at Dark store 07/)).toBeVisible();

    const second = attempts.getByTestId("trace-attempt-2");
    await expect(second.getByText("passed all guardrails")).toBeVisible();
  });

  test("Plan live streams a run into the trace, shows the time elapsed, and keeps the recorded trace in place", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByTestId("trace-attempts")).toBeVisible();
    const recordedRows = await card.locator(".trace-panel .trace-panel__list > li").count();

    await card.getByTestId("plan-live").click();
    await expect(card.getByTestId("plan-live")).toBeDisabled();
    const live = card.getByTestId("live-replan");
    await expect(live).toBeVisible();
    await expect(live.getByText(/\d+ s elapsed/)).toBeVisible();
    await expect(live.locator(".trace-panel__event").first()).toBeVisible({ timeout: 5_000 });
    await expect(live.getByTestId("trace-attempts")).toBeVisible({ timeout: 5_000 });

    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    await expect(card.getByTestId("plan-live")).toBeEnabled();
    await expect(card.locator(".trace-panel .trace-panel__list > li")).toHaveCount(recordedRows);

    // the run's play joins the inbox under a "Live run" tag; the recorded play stays selected
    const inbox = page.getByLabel("Play inbox");
    await expect(inbox.locator(".inbox__live")).toHaveCount(1);
    await expect(card.getByText(/^play_chips_ds07_v1 · status/)).toBeVisible();
    // ... and selecting it shows that play, which Approve then acts on
    await inbox.locator(".inbox__item").filter({ has: page.locator(".inbox__live") }).click();
    await expect(card.getByText(/^play_tea_ds04_v2 · status/)).toBeVisible();
    await expect(card.getByRole("button", { name: "Approve" })).toBeVisible();
  });
});
