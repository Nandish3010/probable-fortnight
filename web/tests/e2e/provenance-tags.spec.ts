import { test, expect, type Locator } from "@playwright/test";
import { approveSettled, assertNoHorizontalOverflow, openBeat } from "./helpers";

// PROJECTED, SYNTHETIC, RECORDED, MEASURED and the "LIVE . SYNTHETIC data" badge have to read in a 1920x1080
// video frame: 14 px or more, weight 600, with padding (a tag is not a text run). Checked on the landing
// card, the Approve result, the Desk play card and Outcomes, and that they still fit at 375 px.

async function expectReadable(tags: Locator, what: string) {
  const n = await tags.count();
  expect(n, `${what}: tags found`).toBeGreaterThan(0);
  for (let i = 0; i < n; i += 1) {
    const css = await tags.nth(i).evaluate((el) => {
      const s = getComputedStyle(el);
      return { text: (el.textContent ?? "").trim(), size: parseFloat(s.fontSize), weight: Number(s.fontWeight), padX: parseFloat(s.paddingLeft) };
    });
    expect(css.size, `${what} "${css.text}" size`).toBeGreaterThanOrEqual(14);
    expect(css.weight, `${what} "${css.text}" weight`).toBeGreaterThanOrEqual(600);
    expect(css.padX, `${what} "${css.text}" padding`).toBeGreaterThanOrEqual(8);
  }
}

for (const vp of [
  { name: "1920", width: 1920, height: 1080 },
  { name: "375", width: 375, height: 812 },
] as const) {
  test.describe(`provenance tags at ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("landing: the hero figure's tags and the chat badge", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByTestId("preview-figure")).toBeVisible();
      await expectReadable(page.getByTestId("preview-figure").locator(".basis"), "hero figure");
      if (vp.width >= 768) await expectReadable(page.locator(".badge--replay, .badge--live").first(), "chat badge");
      await assertNoHorizontalOverflow(page);
    });

    test("Approve result: PROJECTED and the LIVE . SYNTHETIC data badge", async ({ page }) => {
      const card = await openBeat(page);
      await card.getByTestId("approve-button").click();
      await approveSettled(page);
      const result = page.getByTestId("approve-result").first();
      await expectReadable(result.locator(".basis"), "approve result tag");
      await expectReadable(result.locator(".badge--live, .badge--replay").first(), "approve result badge");
      await assertNoHorizontalOverflow(page);
    });

    test("Desk play card: SYNTHETIC and PROJECTED", async ({ page }) => {
      await page.goto("/desk");
      if (vp.width < 768) await page.getByTestId("inbox-row").first().click();
      const detail = page.getByTestId("play-detail");
      await expect(detail).toBeVisible();
      await expectReadable(detail.getByTestId("recovered-figure").locator(".basis"), "desk figure");
      await assertNoHorizontalOverflow(page);
    });

    test("Outcomes: SYNTHETIC badge and the portfolio tags", async ({ page }) => {
      await page.goto("/outcomes");
      await expect(page.getByRole("heading", { level: 1, name: "Outcomes" })).toBeVisible();
      await expectReadable(page.locator(".badge--synthetic").first(), "outcomes badge");
      await expect(page.locator(".basis").first()).toBeVisible();
      await expectReadable(page.locator(".basis"), "outcomes tag");
      await assertNoHorizontalOverflow(page);
    });
  });
}
