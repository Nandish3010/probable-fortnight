import { test, expect } from "@playwright/test";

// Regression test for the "0 days" bug: GapCard's day countdown must come from the server's
// pinned clock (/health -> server_now, 2026-09-12T03:30:00Z in mock mode), never the browser's
// local clock. The demo tenant's gap_chips_ds07 has deadline_date 2026-09-18, so against the
// pinned server clock the gap card must read "6d" / "6 days" regardless of what the browser
// thinks "now" is.
test.describe("GapCard uses the server clock, not the browser clock", () => {
  test("renders the correct day count when the browser clock is wildly wrong", async ({ page }) => {
    // Install a fake browser clock set years in the future, before any page script runs. If
    // GapCard (or daysUntil) ever falls back to `new Date()`, the countdown would go deeply
    // negative and Math.max(days, 0) would floor it to 0 -- reproducing the reported bug.
    await page.clock.install({ time: new Date("2031-01-01T00:00:00Z") });

    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();

    await expect(page.getByTestId("beat-panel")).toBeVisible();

    const statValues = page.locator(".gap-card__stats .stat__value");
    await expect(statValues.nth(2)).toHaveText("6d");
    await expect(page.locator(".gap-card__rule")).toContainText("6 days");
  });
});
