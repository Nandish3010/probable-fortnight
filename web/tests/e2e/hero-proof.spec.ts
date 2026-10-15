import { test, expect, type Page } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, settledRects } from "./helpers";
import { HERO_FACTS, heroProofData, plainProduct } from "../../lib/heroProof";

// The landing's first screen carries the claim in one frame: what Taal is (one sentence), the user named with
// the lot at stake, the projected figure with its tags and the margin over a blanket markdown, the loop, and
// the assurance line. Above the fold at 1920x1080 and at 375x812, readable in a video frame.

const SENTENCE = "Taal spots stock at risk, plans a play with Gemini, a person approves, the offer goes out, and a holdout measures it.";
const USER_LINE = "A dark-store manager clearing 103 packs of Darjeeling tea, 24 days from sell-by, ₹35,020 at stake.";
const ASSURE = "No sign-in. Reset is per visitor. Synthetic data, labelled.";

async function inFold(page: Page, ids: string[], height: number) {
  for (const id of ids) {
    const loc = page.getByTestId(id).first();
    await expect(loc, id).toBeVisible();
    const [r] = await settledRects(loc);
    expect(r.y, `${id} top`).toBeGreaterThanOrEqual(0);
    expect(r.y + r.height, `${id} bottom ${r.y + r.height} in a ${height}px viewport`).toBeLessThanOrEqual(height);
  }
}

for (const vp of [
  { w: 1920, h: 1080 },
  { w: 1280, h: 800 },
  { w: 375, h: 812 },
] as const) {
  test.describe(`the hero at ${vp.w}x${vp.h}`, () => {
    test.use({ viewport: { width: vp.w, height: vp.h } });

    test("sentence, user line, figure with PROJECTED, the markdown margin, the loop and the assurance are above the fold", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(SENTENCE);
      await expect(page.getByTestId("hero-subline")).toHaveText(USER_LINE);
      await expect(page.getByTestId("preview-figure-amount")).toHaveText("₹9,191");
      const figure = page.getByTestId("preview-figure");
      await expect(figure.getByTestId("basis-projected")).toHaveText("PROJECTED");
      await expect(figure.getByTestId("hero-beat")).toHaveText("+₹6,186 vs a blanket markdown");
      await expect(page.getByTestId("hero-assure")).toHaveText(ASSURE);
      await expect(page.getByTestId("loop-strip")).toBeVisible();
      await inFold(page, ["preview-figure", "hero-subline", "loop-strip", "hero-assure"], vp.h);
      // the figure is the loudest thing: a serif at 28 px or more (40 from 768 px)
      const size = await page.getByTestId("preview-figure-amount").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
      expect(size).toBeGreaterThanOrEqual(28);
      await assertNoHorizontalOverflow(page);
    });
  });
}

test.describe("the primary action and the detailed loop", () => {
  test("at 1920x1080 the detailed loop diagram is above the fold too", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/");
    await expect(page.getByTestId("loop-diagram")).toBeVisible();
    // the loop image is loaded (its box is final) before it is measured
    await page.waitForFunction(() => (document.querySelector('[data-testid="loop-diagram"]') as HTMLImageElement | null)?.complete === true);
    const [diagram] = await settledRects(page.getByTestId("loop-diagram"));
    expect(diagram.y + diagram.height).toBeLessThanOrEqual(1080 - 20); // room for the Linux text height (about 15 px taller)
  });

  test("the one filled button is above the fold at 1280x800, with room for the Linux text height", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const [btn] = await settledRects(page.getByRole("button", { name: "Run the 60-second beat" }));
    expect(btn.y + btn.height).toBeLessThanOrEqual(800 - 60);
    await expect(page.locator(".hero__cta")).toHaveCount(1);
  });

  test("with the beat open the hero gives its room back: Approve stays where it was (<= 740)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("preview-figure")).toBeHidden(); // the opened card carries its own figure
    await page.waitForTimeout(600);
    const [approve] = await settledRects(page.getByTestId("approve-button"));
    expect(approve.y).toBeLessThanOrEqual(740); // the same limit as approve-choreography.spec.ts (Linux text runs about 15 px taller)
  });
});

test.describe("where the numbers come from", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a different lot rewrites the user line and the figure; nothing is hard-coded on a loaded page", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const gaps = mockFixture("gaps").map((g: { gap_id: string; units_at_risk: number; rupees_at_stake: number }) =>
      g.gap_id === "gap_tea_ds04" ? { ...g, units_at_risk: 77, rupees_at_stake: 12345 } : g,
    );
    await fakeApi(page, beatHandlers({ "/gaps": okJson(gaps) }));
    await page.goto("/");
    await expect(page.getByTestId("hero-subline")).toContainText("77 packs of Darjeeling tea");
    await expect(page.getByTestId("hero-subline")).toContainText("₹12,345 at stake");
  });

  test("the service does not answer: the recorded flagship's own values show, labelled PROJECTED", async ({ page }) => {
    await forceLiveApi(page, "http://127.0.0.1:59998"); // nothing listens
    await page.goto("/");
    await expect(page.getByTestId("hero-subline")).toHaveText(USER_LINE);
    await expect(page.getByTestId("preview-figure-amount")).toHaveText("₹9,191");
    await expect(page.getByTestId("preview-figure").getByTestId("basis-projected")).toBeVisible();
  });
});

test.describe("the rules (pure)", () => {
  test("the facts-file values are the fallback, and the product name loses its pack size", () => {
    const d = heroProofData(null, null, undefined);
    expect(d.recovered).toBe("₹9,191");
    expect(d.beat).toBe("+₹6,186 vs a blanket markdown");
    expect(d.userLine).toBe(USER_LINE);
    expect(HERO_FACTS.beat_inr).toBe(6186);
    expect(plainProduct("Darjeeling Tea 100G")).toBe("Darjeeling tea");
    expect(plainProduct("Masala Chips 200G")).toBe("Masala chips");
    expect(plainProduct("Cola Zero 500ML")).toBe("Cola zero");
  });
});
