import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";
import {
  TOUR_STEPS,
  clearTourSeen,
  intersects,
  markTourSeen,
  placePopover,
  shouldAutoStart,
  stepAnnouncement,
  tourKey,
  type Rect,
} from "../../lib/tour";

// The guided tour (E5). The suite's default storage state switches the tour off (playwright.config.ts);
// these specs start from an empty one, as a first-time visitor would.
test.use({ storageState: { cookies: [], origins: [] } });

const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 375, height: 812 };
const STEP_TEXT = [
  "This is the decision: stock that will be thrown away.",
  "This is Taal's plan, with its proof.",
  "You approve here. Nothing is sent until you do.",
  "Then see what the customer gets, and how it is measured.",
];

const dialog = (page: Page) => page.getByRole("dialog", { name: "Guided tour" });

/** Lands on the page and gets the decision card on screen (desktop: the beat; phone: the feed loads). */
async function arrive(page: Page, viewport = DESKTOP): Promise<void> {
  await page.setViewportSize(viewport);
  await page.goto("/");
  if (viewport.width >= 768) await page.getByRole("button", { name: "Run the 60-second beat" }).click();
}

async function waitOpen(page: Page): Promise<void> {
  await expect(dialog(page)).toBeVisible({ timeout: 8_000 });
  // placed: the popover is hidden until the first position is computed
  await expect(page.getByTestId("tour")).toHaveCSS("visibility", "visible");
}

/** Boxes of every visible Approve button. */
async function approveBoxes(page: Page): Promise<Rect[]> {
  const out: Rect[] = [];
  const buttons = page.getByTestId("approve-button");
  for (let i = 0; i < (await buttons.count()); i++) {
    const b = buttons.nth(i);
    if (!(await b.isVisible())) continue;
    const box = await b.boundingBox();
    if (box) out.push({ left: box.x, top: box.y, width: box.width, height: box.height });
  }
  return out;
}

async function box(l: Locator): Promise<Rect> {
  const b = await l.boundingBox();
  if (!b) throw new Error("no box");
  return { left: b.x, top: b.y, width: b.width, height: b.height };
}

test.describe("tour: pure logic", () => {
  test("placePopover flips away from Approve and stays on screen", () => {
    const viewport = { w: 1280, h: 800 };
    const size = { w: 340, h: 150 };
    const approve: Rect = { left: 300, top: 600, width: 160, height: 48 };
    // anchored to Approve itself: below would fit but is not allowed to touch it, and neither may the popover sit on it
    const p = placePopover({ anchor: approve, avoid: [approve], size, viewport, topInset: 56 });
    expect(intersects({ left: p.left, top: p.top, width: size.w, height: size.h }, approve)).toBe(false);
    expect(p.left).toBeGreaterThanOrEqual(8);
    expect(p.top).toBeGreaterThanOrEqual(56);
    expect(p.left + size.w).toBeLessThanOrEqual(1280 - 8);
    expect(p.top + size.h).toBeLessThanOrEqual(800 - 8);
    // an anchor above Approve whose "below" spot would cover Approve flips above
    const why: Rect = { left: 300, top: 560, width: 400, height: 24 };
    const q = placePopover({ anchor: why, avoid: [approve], size, viewport, topInset: 56 });
    expect(q.side).not.toBe("below");
    expect(intersects({ left: q.left, top: q.top, width: size.w, height: size.h }, approve, 8)).toBe(false);
  });

  test("with no anchor the card is centred along the bottom, clear of Approve", () => {
    const approve: Rect = { left: 100, top: 740, width: 160, height: 48 };
    const p = placePopover({ anchor: null, avoid: [approve], size: { w: 340, h: 150 }, viewport: { w: 375, h: 812 }, topInset: 56 });
    expect(intersects({ left: p.left, top: p.top, width: 340, height: 150 }, approve)).toBe(false);
  });

  test("once per visitor: the key is namespaced by the visitor id, Reset clears it, the kill switch wins", () => {
    const store = new Map<string, string>();
    const fake = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    };
    expect(shouldAutoStart(fake, "v1")).toBe(true);
    markTourSeen(fake, "v1");
    expect(store.has(tourKey("v1"))).toBe(true);
    expect(shouldAutoStart(fake, "v1")).toBe(false);
    expect(shouldAutoStart(fake, "v2")).toBe(true); // another visitor in the same browser
    clearTourSeen(fake, "v1");
    expect(shouldAutoStart(fake, "v1")).toBe(true);
    store.set("taal_tour_off", "1");
    expect(shouldAutoStart(fake, "v1")).toBe(false);
    expect(shouldAutoStart(null, "v1")).toBe(false); // no storage: never nag
  });

  test("the four steps say what the plan says, and each is announced", () => {
    expect(TOUR_STEPS.map((s) => s.text)).toEqual(STEP_TEXT);
    expect(stepAnnouncement(1)).toBe("Step 2 of 4: This is Taal's plan, with its proof.");
  });
});

test.describe("tour: once per visitor, skip, Esc, reopen", () => {
  test("opens by itself after the beat card is on screen, then never again for this visitor", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.goto("/");
    await page.waitForTimeout(800);
    await expect(dialog(page)).toHaveCount(0); // not before the card is on screen
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await waitOpen(page);
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(dialog(page)).toContainText(STEP_TEXT[0]);
    await expect(dialog(page)).toContainText("Step 1 of 4");
    const visitor = await page.evaluate(() => localStorage.getItem("taal_visitor"));
    expect(await page.evaluate((k) => localStorage.getItem(k) !== null, `taal_tour:${visitor}`)).toBe(true);

    await page.getByTestId("tour-skip").click();
    await expect(dialog(page)).toHaveCount(0);

    await page.reload();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await page.waitForTimeout(1500);
    await expect(dialog(page)).toHaveCount(0);
  });

  test("Skip tour is visible on every step, and Esc closes from any step", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    for (let i = 0; i < 3; i++) {
      await expect(page.getByTestId("tour-skip")).toBeVisible();
      await expect(page.getByTestId("tour-skip")).toHaveText("Skip tour");
      await page.getByTestId("tour-next").click();
      await expect(dialog(page)).toContainText(STEP_TEXT[i + 1]);
    }
    await expect(page.getByTestId("tour-next")).toHaveText("Done");
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
  });

  test("Back goes back, and Done on the last step closes it", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    await expect(page.getByTestId("tour-back")).toHaveCount(0);
    await page.getByTestId("tour-next").click();
    await page.getByTestId("tour-back").click();
    await expect(dialog(page)).toContainText(STEP_TEXT[0]);
    for (let i = 0; i < 3; i++) await page.getByTestId("tour-next").click();
    await page.getByTestId("tour-next").click(); // Done
    await expect(dialog(page)).toHaveCount(0);
  });

  test("Take the tour reopens it from step 1, and focus returns to the link on close", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
    const link = page.getByTestId("take-tour");
    await expect(link).toBeVisible();
    await link.focus();
    await page.keyboard.press("Enter");
    await waitOpen(page);
    await expect(dialog(page)).toContainText(STEP_TEXT[0]);
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
    await expect(link).toBeFocused();
  });

  test("Take the tour before the beat starts the beat and then the tour", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.addInitScript(() => localStorage.setItem("taal_tour_off", "1"));
    await page.goto("/");
    await page.getByTestId("take-tour").click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await waitOpen(page);
    await expect(dialog(page)).toContainText(STEP_TEXT[0]);
  });

  test("the kill switch keeps it from opening by itself but not from the link", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await page.addInitScript(() => localStorage.setItem("taal_tour_off", "1"));
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await page.waitForTimeout(1200);
    await expect(dialog(page)).toHaveCount(0);
  });

  test("Reset demo data makes the visitor new again: the tour opens on the next beat", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    await page.getByTestId("tour-skip").click();
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByRole("dialog", { name: "Reset demo data?" }).getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeVisible();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await waitOpen(page);
    await expect(dialog(page)).toContainText(STEP_TEXT[0]);
  });
});

test.describe("tour: focus", () => {
  test("focus moves in, is trapped while open, and returns to the previous element on close", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    const inside = () => page.evaluate(() => !!document.activeElement?.closest('[data-testid="tour"]'));
    expect(await inside()).toBe(true);
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab");
      expect(await inside(), `Tab ${i + 1} left the tour`).toBe(true);
    }
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press("Shift+Tab");
      expect(await inside(), `Shift+Tab ${i + 1} left the tour`).toBe(true);
    }
    // the landing had put focus on the card title; Esc hands it back
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveCount(0);
    await expect(page.locator("[data-card-title]").first()).toBeFocused();
  });

  test("with the tour closed Tab is untouched and A still jumps to Approve; Enter approves", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    await page.getByTestId("tour-skip").click();
    await expect(dialog(page)).toHaveCount(0);
    const approve = page.getByTestId("beat-panel").getByTestId("approve-button");
    await page.keyboard.press("a");
    await expect(approve).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-testid="approve-result"]')).toBeVisible({ timeout: 30_000 });
    await expect(dialog(page)).toHaveCount(0);
  });

  test("clicking Approve while the tour is open ends the tour", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    await page.getByTestId("beat-panel").getByTestId("approve-button").click();
    await expect(dialog(page)).toHaveCount(0);
    await expect(page.locator('[data-testid="approve-result"]')).toBeVisible({ timeout: 30_000 });
  });

  test("each step is announced in a polite live region", async ({ page }) => {
    await arrive(page);
    await waitOpen(page);
    const live = page.getByTestId("tour-live");
    await expect(live).toHaveAttribute("aria-live", "polite");
    await expect(live).toHaveText("Step 1 of 4: " + STEP_TEXT[0]);
    await page.getByTestId("tour-next").click();
    await expect(live).toHaveText("Step 2 of 4: " + STEP_TEXT[1]);
    await page.getByTestId("tour-next").click();
    await page.getByTestId("tour-next").click();
    await expect(live).toHaveText("Step 4 of 4: " + STEP_TEXT[3]);
  });

  test("reduced motion: the popover has no transition", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await arrive(page);
    await waitOpen(page);
    // globals.css collapses durations to a hair above zero under reduced motion
    const seconds = await page.getByTestId("tour").evaluate((el) => parseFloat(getComputedStyle(el).transitionDuration));
    expect(seconds).toBeLessThan(0.001);
  });
});

for (const [name, viewport] of [["1280x800", DESKTOP], ["375x812", PHONE]] as const) {
  test.describe(`tour: never covers Approve (${name})`, () => {
    test("every step sits on screen and clear of every Approve button", async ({ page }) => {
      await arrive(page, viewport);
      await waitOpen(page);
      for (let i = 0; i < 4; i++) {
        await expect(dialog(page)).toContainText(STEP_TEXT[i]);
        await expect(page.getByTestId("tour")).toHaveCSS("visibility", "visible");
        await page.waitForTimeout(450); // let the late re-measure settle
        const pop = await box(page.getByTestId("tour"));
        const approves = await approveBoxes(page);
        expect(approves.length).toBeGreaterThan(0);
        for (const a of approves) {
          expect(intersects(pop, a), `step ${i + 1}: popover ${JSON.stringify(pop)} covers Approve ${JSON.stringify(a)}`).toBe(false);
        }
        expect(pop.left).toBeGreaterThanOrEqual(0);
        expect(pop.top).toBeGreaterThanOrEqual(0);
        expect(pop.left + pop.width).toBeLessThanOrEqual(viewport.width);
        expect(pop.top + pop.height).toBeLessThanOrEqual(viewport.height);
        if (i < 3) await page.getByTestId("tour-next").click();
      }
    });

    test("step 3 points at Approve and the ring is on it", async ({ page }) => {
      await arrive(page, viewport);
      await waitOpen(page);
      await page.getByTestId("tour-next").click();
      await page.getByTestId("tour-next").click();
      await expect(dialog(page)).toContainText(STEP_TEXT[2]);
      await page.waitForTimeout(450);
      const ring = await box(page.getByTestId("tour-ring"));
      const approve = (await approveBoxes(page))[0];
      expect(intersects(ring, approve)).toBe(true);
    });
  });
}

test("a keyboard user can still reach and press Approve after the tour is skipped (phone)", async ({ page }) => {
  await arrive(page, PHONE);
  await waitOpen(page);
  await page.keyboard.press("Escape");
  const approve = page.getByTestId("feed-item-1").getByTestId("approve-button");
  await approve.focus();
  await expect(approve).toBeFocused();
});

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of [["desktop", DESKTOP], ["phone", PHONE]] as const) {
    test(`axe (${scheme}, ${name}): the tour open on steps 1 and 3 has no violations`, async ({ browser }) => {
      const context = await browser.newContext({ viewport, colorScheme: scheme, reducedMotion: "reduce", storageState: { cookies: [], origins: [] } });
      const page = await context.newPage();
      await arrive(page, viewport);
      await waitOpen(page);
      await page.waitForTimeout(450);
      const tags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
      let results = await new AxeBuilder({ page }).withTags(tags).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      await page.getByTestId("tour-next").click();
      await page.getByTestId("tour-next").click();
      await page.waitForTimeout(450);
      results = await new AxeBuilder({ page }).withTags(tags).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      await context.close();
    });
  }
}

test("360 px: no horizontal overflow with the tour open on any step, and the card stays on screen", async ({ page }) => {
  const viewport = { width: 360, height: 800 };
  await arrive(page, viewport);
  await waitOpen(page);
  for (let i = 0; i < 4; i++) {
    await page.waitForTimeout(450);
    await assertNoHorizontalOverflow(page);
    const pop = await box(page.getByTestId("tour"));
    expect(pop.left).toBeGreaterThanOrEqual(0);
    expect(pop.left + pop.width).toBeLessThanOrEqual(360);
    for (const a of await approveBoxes(page)) expect(intersects(pop, a)).toBe(false);
    if (i < 3) await page.getByTestId("tour-next").click();
  }
});
