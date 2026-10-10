import { test, expect, type Page } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";

// The stepper on a phone: the same five links as equal columns, dot over label, in one bar. Pixel 7
// project (412 px); the describe below shrinks it to a small Android phone.

const stepper = (page: Page) => page.getByTestId("stepper");

async function expectFitsInOneBar(page: Page) {
  const viewport = page.viewportSize()!.width;
  const items = stepper(page).locator("li");
  await expect(items).toHaveCount(5);
  const boxes = await items.evaluateAll((lis) =>
    lis.map((li) => {
      const link = li.querySelector("a")!.getBoundingClientRect();
      const label = li.querySelector<HTMLElement>('[data-part="label"]')!;
      return { l: link.left, r: link.right, t: link.top, b: link.bottom, h: link.height, labelClipped: label.scrollWidth > label.clientWidth + 0.5, label: label.textContent };
    }),
  );
  for (const b of boxes) {
    expect(b.labelClipped, `${b.label} is clipped`).toBe(false);
    expect(b.l, `${b.label} starts on screen`).toBeGreaterThanOrEqual(0);
    expect(b.r, `${b.label} ends on screen`).toBeLessThanOrEqual(viewport);
    expect(b.h, `${b.label} tap target`).toBeGreaterThanOrEqual(44);
  }
  // one row: every link is on the same line
  expect(Math.max(...boxes.map((b) => b.t)) - Math.min(...boxes.map((b) => b.t))).toBeLessThan(4);
  // left to right in order, no overlaps
  for (let i = 1; i < boxes.length; i += 1) expect(boxes[i].l).toBeGreaterThanOrEqual(boxes[i - 1].r - 1);
  // the brand shares the bar
  const brand = (await page.locator("header.top-nav .top-nav__brand").boundingBox())!;
  expect(brand.x + brand.width).toBeLessThanOrEqual(boxes[0].l + 1);
  await assertNoHorizontalOverflow(page);
}

test.describe("stepper on a phone", () => {
  test("five steps in one bar, labels whole, 44 px targets, the current step marked", async ({ page }) => {
    await page.goto("/");
    await expectFitsInOneBar(page);
    await expect(stepper(page).locator('li [data-part="label"]')).toHaveText(["Spot", "Plan", "Approve", "Offer", "Measure"]);
    await expect(stepper(page).locator('[aria-current="step"]')).toHaveCount(1);
    await expect(stepper(page).locator('[aria-current="step"]')).toContainText("Approve");
    // no persona caption on a phone: the link's name still carries it
    await expect(stepper(page).locator('[data-part="caption"]').first()).toBeHidden();
    await expect(stepper(page).getByRole("link", { name: "Plan: Play Desk (Arjun)" })).toBeVisible();
  });

  test("the bar fits on every screen of the path, and in the locked and done states", async ({ page }) => {
    for (const route of ["/desk", "/phone", "/chat", "/outcomes"]) {
      await page.goto(route);
      await expectFitsInOneBar(page);
    }
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_approved", JSON.stringify(["play_tea_ds04_v1"])));
    await page.goto("/");
    await expect(stepper(page).locator('li[data-step="approve"]')).toHaveAttribute("data-done", "true");
    await expectFitsInOneBar(page);
  });

  test("tapping a step goes to its screen", async ({ page }) => {
    await page.goto("/");
    await stepper(page).getByRole("link", { name: /^Spot/ }).click();
    await expect(page).toHaveURL(/\/phone$/);
    await stepper(page).getByRole("link", { name: /^Plan/ }).click();
    await expect(page).toHaveURL(/\/desk$/);
  });

  test("a locked step is still a link on a phone", async ({ page }) => {
    await page.goto("/");
    await expect(stepper(page).locator('li[data-step="measure"]')).toHaveAttribute("data-state", "locked");
    await stepper(page).getByRole("link", { name: /^Measure/ }).click();
    await expect(page).toHaveURL(/\/outcomes$/);
  });
});

test.describe("stepper on a small phone (360 px)", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("fits in one bar with whole labels", async ({ page }) => {
    for (const route of ["/", "/desk", "/outcomes"]) {
      await page.goto(route);
      await expectFitsInOneBar(page);
    }
  });
});
