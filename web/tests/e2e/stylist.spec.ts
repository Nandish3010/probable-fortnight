import path from "node:path";
import { test, expect } from "@playwright/test";

const MUSTARD_KURTA_PNG = path.join(__dirname, "../../../fixtures/photos/garments/mustard_kurta.png");

test.describe("stylist: pairings and photo upload", () => {
  test("paints with no console errors and a text ask returns pairings", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/stylist");
    await expect(page.getByRole("heading", { name: "Style assistant" })).toBeVisible();

    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log").first();
    await expect(log).toContainText(/kurta/i, { timeout: 6_000 });
    await expect(log).toContainText(/complementary|neutral anchor|analogous/i);
    expect(errors).toEqual([]);
  });

  test("uploading a garment photo returns pairings for it", async ({ page }) => {
    await page.goto("/stylist");
    await page.getByTestId("garment-photo").setInputFiles(MUSTARD_KURTA_PNG);
    await expect(page.getByText(/photo attached/i)).toBeVisible();

    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log").first();
    await expect(log).toContainText(/kurta/i, { timeout: 6_000 });
  });

  test("picking a sample garment photo needs no file dialog", async ({ page }) => {
    await page.goto("/stylist");
    await page.getByTestId("sample-garment-choices").getByRole("button", { name: "Mustard kurta" }).click();
    await expect(page.getByText(/photo attached/i)).toBeVisible();

    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log").first();
    await expect(log).toContainText(/kurta/i, { timeout: 6_000 });
  });
});

test.describe("trends: recompute button", () => {
  test("shows the trend row and recompute reports a count", async ({ page }) => {
    await page.goto("/trends");
    await expect(page.getByRole("heading", { name: "Style trends" })).toBeVisible();
    await expect(page.getByText("kurta").first()).toBeVisible();

    await page.getByRole("button", { name: "Recompute trends" }).click();
    await expect(page.getByText(/rows?/)).toBeVisible();
  });
});
