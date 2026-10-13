import { test, expect } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";

test.describe("landing on a phone: loop diagram", () => {
  // The diagram is hidden at 640 px and below (page.module.css): too small to read, and it pushed the decision down.
  test("it is not shown at 640 px and below, and the page does not scroll sideways", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("decision-feed")).toBeVisible();
    await expect(page.getByTestId("loop-diagram")).toBeHidden();
    await assertNoHorizontalOverflow(page);
  });

  test("between 641 and 767 px it is full width and does not push the page sideways", async ({ page }) => {
    await page.setViewportSize({ width: 700, height: 900 });
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
