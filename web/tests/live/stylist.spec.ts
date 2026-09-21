import { test, expect } from "@playwright/test";
import { asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot } from "./helpers";

// Stylist chat against the real stack: a sample-garment pick, then a real pairing reply, with the
// sample-garment picker still visible (screenshot evidence for docs/screenshots/).
test.describe("Stylist: chat", () => {
  test("sample garment pick returns a real pairing, picker stays visible", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-stylist");
    await page.goto("/stylist");
    await expect(page.getByRole("heading", { name: "Style assistant" })).toBeVisible();

    await page.getByTestId("sample-garment-choices").getByRole("button", { name: "Mustard kurta" }).click();
    await expect(page.getByText(/photo attached/i)).toBeVisible();
    await shot(page, "stylist-01-picker");

    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log").first();
    await expect(log).toContainText(/kurta/i, { timeout: 15_000 });
    await expect(log).toContainText(/complementary|neutral anchor|analogous/i);
    await shot(page, "stylist-02-pairing");
    await expectNoConsoleErrors(errors);
  });
});
