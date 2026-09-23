import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

test.describe("Priya: phone view", () => {
  test("pallet photo, confirmation, gap card, approve, execution", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-priya");
    await page.goto("/phone");
    await expect(page.getByRole("heading", { name: "Priya's phone" })).toBeVisible();
    await shot(page, "priya-01-phone");

    for (const label of ["Pallet 2", "Pallet 3"]) {
      await page.getByRole("button", { name: label }).click();
      await expect(page.getByTestId("intake-table")).toBeVisible();
    }
    await page.getByRole("button", { name: "Pallet 1" }).click();
    const table = page.getByTestId("intake-table");
    // This real, live-Gemini-verified pallet photo reads with high confidence on every row
    // (eval/evaluation.md, "Regenerated the three demo pallet fixtures"): the third row read as
    // the real, valid SKU SKU-BANANA-CHIPS-200G rather than the originally intended -100G, and
    // no row needs a confirmation question before confirming.
    await expect(table.getByText("SKU-BANANA-CHIPS-200G")).toBeVisible();
    await shot(page, "priya-02-intake");
    const confirmed = page.waitForResponse((r) => r.url().endsWith("/capture/confirm"));
    await page.getByRole("button", { name: "Confirm rows" }).click();
    // all three rows (all high-confidence) become photo-sourced inventory; gaps are re-detected
    // for the node on the spot (these small lots sell through, so no new gap is right)
    const body = await (await confirmed).json();
    expect(body.ok).toBeTruthy();
    expect(body.written).toBe(3);
    expect(body.batches.every((b: { source: string; online_sellby_date: string; expiry_date: string }) => b.source === "photo" && b.online_sellby_date <= b.expiry_date)).toBeTruthy();
    const gaps = await (await page.request.get(`${API}/gaps?node_id=DS-07&limit=500`, { headers: visitorHeaders("live-priya") })).json();
    expect(gaps.some((g: { gap_id: string }) => g.gap_id === "gap_chips_ds07")).toBeTruthy();
    await expect(page.getByText("₹9,200")).toBeVisible();
    await expect(page.getByText(/6 days/)).toBeVisible();
    await shot(page, "priya-03-gap-card");

    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Execution steps" })).toBeVisible();
    await shot(page, "priya-04-approved");
    const labels = page.locator(".execution-steps label");
    const n = await labels.count();
    expect(n).toBeGreaterThan(0);
    for (let i = 0; i < n; i++) await labels.nth(i).click();
    await expect(page.locator(".execution-steps input:checked")).toHaveCount(n);
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByText(/exec_play_chips_ds07_v1|Recorded|recorded/)).toBeVisible();
    await shot(page, "priya-05-execution");

    // microphone is a documented stub
    const mic = page.getByRole("button", { name: /mic|voice/i });
    if (await mic.count()) await expect(mic.first()).toBeDisabled();
    await expectNoConsoleErrors(errors);
  });
});
