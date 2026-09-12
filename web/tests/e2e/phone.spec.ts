import { test, expect } from "@playwright/test";

test.describe("phone view", () => {
  test("sample photo -> table -> confirm -> gap card -> approve -> chart", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/phone");

    await page.getByRole("button", { name: "Pallet 1" }).click();

    const table = page.getByTestId("intake-table");
    await expect(table).toBeVisible();
    await expect(table.getByText("SKU-MASALA-CHIPS-200G")).toBeVisible();
    await expect(table.getByText("SKU-SALTED-CHIPS-200G")).toBeVisible();
    await expect(table.getByText("SKU-BANANA-CHIPS-100G")).toBeVisible();

    await page.getByRole("button", { name: "Yes" }).click();

    await page.getByRole("button", { name: "Confirm rows" }).click();

    await expect(page.getByText("₹9,200")).toBeVisible();

    await page.getByRole("button", { name: "Approve" }).click();

    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });

    expect(errors).toEqual([]);
  });
});
