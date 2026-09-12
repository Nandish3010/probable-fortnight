import { test, expect } from "@playwright/test";

test.describe("judge-mode landing", () => {
  test("paints with no console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/");
    await expect(page.getByText("Taal judge mode")).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("60-second beat: gap card, approve, chart", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();

    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByText("₹9,200")).toBeVisible();

    await page.getByRole("button", { name: "Approve" }).click();

    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("writeoff-line")).toContainText("→", { timeout: 30_000 });
  });

  test("chat as Meena responds within 6s", async ({ page }) => {
    await page.goto("/");
    const log = page.getByTestId("chat-log").first();
    await page.getByRole("button", { name: "Send" }).first().click();

    await expect(log).toContainText(/Best before|ಬಳಕೆಗೆ/, { timeout: 6_000 });
  });
});
