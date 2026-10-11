import { test, expect } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";

test.describe("landing on a phone: loop diagram", () => {
  test("it is full width and does not push the page sideways", async ({ page }) => {
    await page.goto("/");
    const img = page.getByTestId("loop-diagram");
    await expect(img).toBeVisible();
    const [imgW, mainW] = await Promise.all([
      img.evaluate((el) => el.getBoundingClientRect().width),
      page.locator("main").evaluate((el) => el.getBoundingClientRect().width),
    ]);
    expect(imgW).toBeGreaterThan(mainW * 0.85);
    await assertNoHorizontalOverflow(page);
  });
});
