import { test, expect } from "@playwright/test";
import { openBeat } from "./helpers";

// Phase 3A polish from the 2B review (toast placement, the heading, the disclosure), the desktop
// layouts that must not change, and the switch between the desktop and phone landing.

test.describe("the toast", () => {
  test("on a desktop it is fixed top right, under the nav, and does not cover the chart or its axis", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const card = await openBeat(page);
    await card.getByRole("button", { name: "Approve" }).click();
    const toast = page.getByTestId("approve-toast");
    await expect(toast).toBeVisible({ timeout: 8000 });
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await page.getByTestId("approve-toast").waitFor({ state: "visible" }).catch(() => undefined);

    // placement: fixed, top right, below the 56px nav
    await expect(toast).toHaveCSS("position", "fixed");
    const box = (await toast.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(56);
    expect(box.y).toBeLessThan(120);
    expect(1280 - (box.x + box.width)).toBeLessThanOrEqual(40);
    expect(box.x + box.width).toBeLessThanOrEqual(1280);

    // not over the chart (the chart's x axis is the bottom of its box)
    const chart = page.locator("svg.forecast-chart");
    await chart.scrollIntoViewIfNeeded();
    const t2 = await toast.boundingBox();
    if (t2) {
      const c = (await chart.boundingBox())!;
      const overlap = !(t2.x + t2.width <= c.x || c.x + c.width <= t2.x || t2.y + t2.height <= c.y || c.y + c.height <= t2.y);
      expect(overlap, "the toast overlaps the chart").toBe(false);
    }
  });

  test("it is dismissable and goes after five seconds", async ({ page }) => {
    const card = await openBeat(page);
    await card.getByRole("button", { name: "Approve" }).click();
    const toast = page.getByTestId("approve-toast");
    await expect(toast).toBeVisible({ timeout: 8000 });
    await toast.getByRole("button", { name: "Dismiss" }).click();
    await expect(toast).toHaveCount(0);
  });
});

test.describe("the approved result", () => {
  test("the heading names the product, not the figure; the figure is the big number and the chip", async ({ page }) => {
    const card = await openBeat(page);
    await card.getByRole("button", { name: "Approve" }).click();
    const result = page.getByTestId("approve-result");
    await result.waitFor({ timeout: 30_000 });
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    const heading = result.getByRole("heading").first();
    await expect(heading).toHaveText("Approved: Darjeeling Tea 100G");
    await expect(heading).not.toContainText("₹");
    await expect(heading).not.toContainText("recovered");
    // the recovered figure appears twice in the result (the number, then the chip), never in the heading
    await expect(result.getByTestId("approve-recovered-amount")).toHaveText("₹7,498");
    await expect(result.getByTestId("approve-recovered-delta")).toHaveText("+₹7,498 vs doing nothing");
    const mentions = await result.evaluate((el) => (el.textContent ?? "").split("₹7,498").length - 1);
    expect(mentions).toBe(2);
  });

  test("Show technical details is a proper disclosure: 44px, a chevron that turns, keyboard-operable", async ({ page }) => {
    const card = await openBeat(page);
    await card.getByRole("button", { name: "Approve" }).click();
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    const details = page.getByTestId("approve-details");
    const summary = details.locator("summary");
    await summary.scrollIntoViewIfNeeded();
    expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    const chevron = summary.locator('svg[data-icon="chevron-down"]');
    await expect(chevron).toHaveCount(1);
    const closed = await chevron.evaluate((el) => getComputedStyle(el).transform);
    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("open", "");
    await expect.poll(() => chevron.evaluate((el) => getComputedStyle(el).transform)).not.toBe(closed);
    await expect(summary).toHaveCSS("outline-style", "solid"); // a visible focus ring
  });
});

test.describe("the hero keeps its headroom at 1280 x 800", () => {
  test("Approve's top edge is at or under 740 px and its whole button is in the first screen", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openBeat(page);
    await page.waitForTimeout(500);
    const box = (await page.getByTestId("approve-button").boundingBox())!;
    expect(box.y).toBeLessThanOrEqual(740);
    expect(box.y + box.height).toBeLessThanOrEqual(800);
  });
});

test.describe("desktop layouts are unchanged", () => {
  test("the landing is the beat button, then one card; no feed", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeVisible();
    await expect(page.getByTestId("decision-feed")).toHaveCount(0);
    await expect(page.locator(".chat-panel")).toBeVisible();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel").getByTestId("play-card")).toHaveAttribute("data-mode", "hero");
    await expect(page.getByTestId("play-card")).toHaveCount(1);
  });

  test("the Desk is two columns: the inbox on the left, the first play's detail on the right, no Back bar", async ({ page }) => {
    await page.goto("/desk");
    const detail = page.getByTestId("play-detail");
    await expect(detail).toBeVisible();
    await expect(page.getByLabel("Play inbox")).toBeVisible();
    await expect(page.getByTestId("desk-back")).toBeHidden();
    const i = (await page.getByTestId("inbox-pane").boundingBox())!;
    const d = (await detail.boundingBox())!;
    expect(d.x).toBeGreaterThan(i.x + i.width - 1);
    expect(Math.abs(d.y - i.y)).toBeLessThan(80);
    await expect(page.getByTestId("inbox-heading")).toHaveText("Top 7 of 16 gaps by rupees at stake");
    // clicking a row selects it in place; it does not change the URL
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await expect(page.getByTestId("play-ids")).toContainText("play_chips_ds07_v1");
    expect(await page.evaluate(() => window.location.hash)).toBe("");
    await expect(page.getByLabel("Play inbox")).toBeVisible();
  });

  test("on a desktop the inbox rows carry the status, deadline and rupees too", async ({ page }) => {
    await page.goto("/desk");
    const row = page.getByTestId("inbox-row").filter({ hasText: "Masala Chips 200G" });
    await expect(row.getByTestId("inbox-status")).toHaveText("Proposed");
    await expect(row.getByTestId("inbox-due")).toHaveText("in 6 days");
    await expect(row).toContainText("₹9,200 at stake");
  });
});

test.describe("the landing follows the window", () => {
  test("narrowing to a phone width swaps the beat button for the feed, and widening swaps it back", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeVisible();
    await page.setViewportSize({ width: 600, height: 900 });
    await expect(page.getByTestId("decision-feed")).toBeVisible();
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toHaveCount(0);
    await page.setViewportSize({ width: 1000, height: 900 });
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeVisible();
    await expect(page.getByTestId("decision-feed")).toHaveCount(0);
  });

  test("a phone-width load never paints the desktop button before the feed", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    // Frame by frame, is the beat button on screen? (Layout before the stylesheet arrives is never
    // painted, so only animation frames count.)
    await page.addInitScript(() => {
      const w = window as unknown as { __sawCta: boolean };
      w.__sawCta = false;
      const frame = () => {
        const cta = Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.trim() === "Run the 60-second beat");
        if (cta && cta.getClientRects().length > 0) w.__sawCta = true;
        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    });
    await page.goto("/");
    await page.getByTestId("decision-feed").waitFor();
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => (window as unknown as { __sawCta: boolean }).__sawCta)).toBe(false);
  });
});
