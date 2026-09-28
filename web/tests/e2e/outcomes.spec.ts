import { test, expect } from "@playwright/test";

test.describe("outcomes: measure button", () => {
  test("Run Measure is clickable and reports a summary", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/outcomes");
    await expect(page.getByRole("heading", { name: "Outcomes" })).toBeVisible();
    await expect(page.getByText("SKU-MASALA-CHIPS-200G").first()).toBeVisible();

    await page.getByRole("button", { name: "Run Measure" }).click();
    await expect(page.getByText(/plays? joined against orders/)).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe("outcomes: estimator prior on the featured play", () => {
  test("the prior update line shows on the featured card and survives Reset", async ({ page }) => {
    const line = /Estimator prior: Beta\(1,19\) → Beta\(17,319\) · SYNTHETIC orders/;
    await page.goto("/outcomes");
    const card = page.locator(".card", { hasText: "Worked example: SKU-MASALA-CHIPS-200G" });
    await expect(card.getByText(line)).toBeVisible();
    await expect(card.locator(".prior-update .badge--synthetic")).toHaveText("SYNTHETIC");

    await page.goto("/");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await expect(page.getByRole("button", { name: "Reset demo data" })).toBeEnabled();
    await page.goto("/outcomes");
    await expect(page.locator(".card", { hasText: "Worked example: SKU-MASALA-CHIPS-200G" }).getByText(line)).toBeVisible();
  });
});
