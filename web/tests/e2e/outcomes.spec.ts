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
