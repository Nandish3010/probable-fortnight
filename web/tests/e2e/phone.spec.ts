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
    // product names, not sku ids; the id of each row is inside its "id" disclosure
    await expect(table.getByText("Masala Chips 200G", { exact: true })).toBeVisible();
    await expect(table.getByText("Salted Chips 200G", { exact: true })).toBeVisible();
    await expect(table.getByText("Banana Chips 200G", { exact: true })).toBeVisible();
    await table.locator("tbody tr").first().locator("summary").click();
    await expect(table.locator("tbody tr").first()).toContainText("SKU-MASALA-CHIPS-200G");

    // This real, live-Gemini-verified pallet photo reads with high confidence on every row, so
    // there is no confirmation question to answer before confirming.
    await page.getByRole("button", { name: "Confirm rows" }).click();

    await expect(page.getByTestId("why-now")).toContainText("₹9,200");

    await page.getByRole("button", { name: "Approve" }).click();

    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });

    expect(errors).toEqual([]);
  });

  test("a sample with an unclear date routes one row to the confirm step, and Confirm rows waits for the answer", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 6" }).click();

    const table = page.getByTestId("intake-table");
    await expect(table.getByText("Wheat Atta 1KG", { exact: true })).toBeVisible();
    await expect(table.getByText("Poha 500G", { exact: true })).toBeVisible();
    // the atta row clears the 70% threshold; the poha row (date 65%) does not and is asked about
    await expect(table.getByText(/date 65%/)).toBeVisible();
    await expect(table.locator(".confirm-row")).toHaveCount(1);
    await expect(table.locator(".confirm-row")).toContainText("Is this Poha 500G");

    const confirm = page.getByRole("button", { name: "Confirm rows" });
    await expect(confirm).toBeDisabled();
    await table.locator(".confirm-row").getByRole("button", { name: "Yes" }).click();
    await expect(confirm).toBeEnabled();
    await confirm.click();
    await expect(page.getByText(/Wrote \d+ batch/)).toBeVisible();

    // Neither pallet SKU raised a gap: the page says so instead of showing the node's top gap.
    await expect(page.getByTestId("phone-no-risk")).toContainText("No sell-by risk for these items");
    await expect(page.getByTestId("gap-fallback-note")).toHaveCount(0);
    await page.getByRole("button", { name: "See the node's biggest open gap" }).click();
    await expect(page.getByTestId("gap-fallback-note")).toHaveText(
      "None of the photographed items raised a gap. Showing the node's biggest open gap instead.",
    );
  });

  test("when a photographed SKU did raise the gap, there is no fallback note", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await expect(page.getByTestId("why-now")).toContainText("₹9,200");
    await expect(page.getByTestId("gap-fallback-note")).toHaveCount(0);
    await expect(page.getByTestId("phone-no-risk")).toHaveCount(0);
  });
});
