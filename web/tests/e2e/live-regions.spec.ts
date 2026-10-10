import { test, expect } from "@playwright/test";

// UX fixes for a judge using a screen reader: the chat transcript is an ARIA log region, the
// Approve result and the re-plan result are ARIA status regions, and focus moves to the approve
// result's heading once it renders. Verified against the real accessibility tree via Playwright's
// ARIA snapshot API (locator.ariaSnapshot()), not just the raw `role`/`aria-live` attributes.
test.describe("live regions: chat log", () => {
  test("chat message list is an ARIA log region", async ({ page }) => {
    await page.goto("/chat");
    const log = page.getByTestId("chat-log");
    await expect(log).toHaveAttribute("aria-live", "polite");

    const snapshot = await log.ariaSnapshot();
    expect(snapshot.trim().startsWith("- log")).toBe(true);
  });
});

test.describe("live regions: Desk approve result", () => {
  test("Approve announces a status region and moves focus to its heading", async ({ page }) => {
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");

    await card.getByRole("button", { name: "Approve" }).click();
    const result = page.getByTestId("approve-result");
    await expect(result).toBeVisible({ timeout: 15_000 });
    // The result block is not itself a live region any more: the panel's one persistent region
    // (#approve-live) announces the outcome, so the same words are not read twice.
    await expect(result).not.toHaveAttribute("role", "status");
    await expect(page.locator("#approve-live")).toHaveAttribute("role", "status");
    await expect(page.locator("#approve-live")).toContainText("Approved. Recovered versus doing nothing", { timeout: 15_000 });

    // Focus lands on the result heading, not just "somewhere" -- the concrete a11y contract.
    const heading = result.getByRole("heading", { name: /Approved/ });
    await expect(heading).toBeFocused();

    const snapshot = await result.ariaSnapshot();
    expect(snapshot).not.toContain("- status");
    expect(snapshot).toContain("heading");

    // The forecast chart is a labelled image (role=img + aria-label, ForecastChart.tsx) with a text
    // summary, never the SVG's raw <text> labels or dates -- those are presentational children of an
    // img and do not get their own accessibility-tree nodes.
    expect(snapshot).toContain("Forecast chart");
    expect(snapshot).not.toContain("Without the play");
    expect(snapshot).not.toContain("Units per day");
  });
});

test.describe("live regions: Desk re-plan result", () => {
  test("a re-plan announces a status region for its result", async ({ page }) => {
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");

    await card.getByRole("button", { name: /Change policy/ }).click();
    const resultSection = card.locator(".play-card__section").filter({ hasText: "Re-plan result" });
    await expect(resultSection.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    await expect(resultSection).toHaveAttribute("role", "status");

    const snapshot = await resultSection.ariaSnapshot();
    expect(snapshot.trim().startsWith("- status")).toBe(true);
    expect(snapshot).toContain("Re-plan result");
  });
});
