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
});
