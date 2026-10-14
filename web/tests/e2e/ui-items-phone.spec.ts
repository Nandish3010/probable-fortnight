import { test, expect } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";

test.describe("landing on a phone: detailed loop diagram", () => {
  // The diagram is hidden at 640 px and below (page.module.css): too small to read, and it pushed the decision down.
  // The one-line loop strip above the decision carries the loop there (hero-live.spec.ts).
  test("it is not shown at 640 px and below, and the page does not scroll sideways", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("decision-feed")).toBeVisible();
    await expect(page.getByTestId("loop-diagram")).toBeHidden();
    await expect(page.getByTestId("loop-strip")).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  test("between 641 and 767 px it is full width and does not push the page sideways", async ({ page }) => {
    await page.setViewportSize({ width: 700, height: 900 });
    await page.goto("/");
    // Hydration has finished once the phone layout is mounted; the image is measured only after it has
    // loaded, so the box is read from a settled page and not from a node that is about to be swapped.
    await expect(page.getByTestId("phone-landing")).toBeVisible();
    const img = page.getByTestId("loop-diagram");
    await expect(img).toBeVisible();
    await expect
      .poll(() => img.evaluate((el: HTMLImageElement) => el.isConnected && el.complete && el.naturalWidth > 0))
      .toBe(true);
    const [imgW, mainW] = await Promise.all([
      img.evaluate((el) => el.getBoundingClientRect().width),
      page.locator("main").evaluate((el) => el.getBoundingClientRect().width),
    ]);
    expect(imgW).toBeGreaterThan(mainW * 0.85);
    await assertNoHorizontalOverflow(page);
  });
});
