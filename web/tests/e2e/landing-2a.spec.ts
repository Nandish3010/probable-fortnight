import { test, expect } from "@playwright/test";
import { mockCalls } from "./helpers";

// Phase 2A landing: hero line, the 4-step strip, the demo-clock chip, relative dates, the state
// legend with its tooltips, Reset behind a confirm dialog at the end of the tab order, the
// prefetched beat, and the inline SVG icons.

const HERO_LINE =
  "Taal finds the stock you will throw away and sells it first: legally, to the right people, with a holdout to prove it.";

test.describe("landing: hero, strip, clock, legend", () => {
  test("the hero line is the one h1 and comes before everything else on the page", async ({ page }) => {
    await page.goto("/");
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toHaveCount(1);
    await expect(h1).toHaveText(HERO_LINE);
    // the FSSAI wording is softened and lives in the card's Details, never in the hero
    await expect(h1).not.toContainText("FSSAI");
    const h1BeforeEverything = await page.evaluate(() => {
      const main = document.querySelector("main")!;
      const h1 = main.querySelector("h1")!;
      const others = Array.from(main.querySelectorAll("a, button, summary, h2, h3, ol, ul"));
      return others.every((el) => !!(h1.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING));
    });
    expect(h1BeforeEverything).toBe(true);
  });

  test("the stepper replaces the old strip: five linked steps, the landing's own step is current", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("step-strip")).toHaveCount(0);
    const stepper = page.getByTestId("stepper");
    await expect(stepper.locator("li")).toHaveCount(5);
    await expect(stepper.locator('li [data-part="label"]')).toHaveText(["Spot", "Plan", "Approve", "Offer", "Measure"]);
    await expect(stepper.locator('[aria-current="step"]')).toHaveCount(1);
    await expect(stepper.locator('[aria-current="step"]')).toContainText("Approve");
  });

  test("the demo-clock chip shows the server's date, not the browser's", async ({ page }) => {
    await page.clock.install({ time: new Date("2031-01-01T00:00:00Z") });
    await page.goto("/");
    await expect(page.getByTestId("demo-clock")).toHaveText("Demo date: 12 Sep 2026. Nothing you do here persists.");
    await expect(page.getByTestId("demo-clock")).toHaveAttribute("title", /fixed date/);
  });

  test("deadlines read as relative days with the full date in the tooltip", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const why = page.getByTestId("why-now");
    await expect(why).toContainText("in 24 days (6 Oct)");
    await expect(why).toHaveAttribute("title", "Deadline: Tue 6 Oct 2026");
  });

  test("the legend explains LIVE, REPLAY and SYNTHETIC, and every badge carries its own tooltip", async ({ page }) => {
    await page.goto("/");
    const legend = page.getByTestId("state-legend");
    const summaryBadges = legend.locator("summary .badge");
    await expect(summaryBadges).toHaveCount(3);
    await expect(summaryBadges.nth(0)).toHaveAttribute("title", "Computed just now by Taal's running services.");
    await expect(summaryBadges.nth(1)).toHaveAttribute("title", "A real run, recorded earlier and played back. Nothing was recomputed.");
    await expect(summaryBadges.nth(2)).toHaveAttribute("title", "Seeded demo data for the fictional tenant Kutumb Mart. No real customers.");
    // a tooltip is not enough on a phone: opening the element prints the sentences
    await expect(legend.getByText("A real run, recorded earlier and played back.")).toBeHidden();
    await legend.locator("summary").click();
    await expect(legend.getByText("A real run, recorded earlier and played back. Nothing was recomputed.")).toBeVisible();
    // the chat badge no longer says "Chat as Meena"; it says what REPLAY means
    const chatBadge = page.locator(".chat-panel .badge").first();
    await expect(chatBadge).toHaveAttribute("title", /recorded earlier|Computed just now/);
  });
});

test.describe("landing: Reset demo data", () => {
  test("is in the footer, after the beat button in the tab order, and asks before it clears anything", async ({ page }) => {
    await page.goto("/");
    const reset = page.getByRole("button", { name: "Reset demo data" });
    await expect(reset).toHaveCount(1);
    expect(await reset.evaluate((el) => !!el.closest("footer"))).toBe(true);

    // DOM order == tab order (no positive tabindex): the beat button precedes Reset
    const order = await page.evaluate(() => {
      const els = Array.from(
        document.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), summary, input, select, textarea, [tabindex]"),
      ).filter((e) => e.getClientRects().length > 0); // closed dialog and closed <details> content are not tab stops
      const idx = (pred: (e: HTMLElement) => boolean) => els.findIndex(pred);
      return {
        beat: idx((e) => e.textContent?.trim() === "Run the 60-second beat"),
        reset: idx((e) => e.textContent?.trim() === "Reset demo data"),
        last: els.length - 1,
        positiveTabindex: els.some((e) => Number(e.getAttribute("tabindex")) > 0),
      };
    });
    expect(order.beat).toBeGreaterThanOrEqual(0);
    expect(order.reset).toBeGreaterThan(order.beat);
    expect(order.reset).toBe(order.last); // nothing focusable follows it
    expect(order.positiveTabindex).toBe(false);

    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await reset.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Reset demo data?");
    await expect(dialog).toContainText("This clears your plans and chat for this session.");

    // Cancel (and Escape) change nothing and give focus back to the Reset button
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
    await expect(reset).toBeFocused();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    expect(await mockCalls(page, "/reset")).toBe(0);

    await reset.click();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    expect(await mockCalls(page, "/reset")).toBe(0);

    // Confirming resets and returns to the start of the beat
    await reset.click();
    await dialog.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText(/Reset done for visitor/)).toBeVisible();
    await expect(page.getByTestId("beat-panel")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeVisible();
    expect(await mockCalls(page, "/reset")).toBe(1);
  });

  test("while the dialog is open, Tab never reaches the page behind it", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    const dialog = page.getByRole("dialog");
    for (let i = 0; i < 4; i++) {
      await page.keyboard.press("Tab");
      // a modal <dialog> makes the page inert: focus is in the dialog, or has left the page for the
      // browser's own chrome (activeElement is then <body>); it is never on an element behind it
      expect(await page.evaluate(() => !!document.activeElement?.closest("dialog") || document.activeElement === document.body)).toBe(true);
    }
  });
});

test.describe("landing: the beat is prefetched", () => {
  test("the hero gap and play are read on load, and the click does not read them again", async ({ page }) => {
    await page.goto("/");
    await expect.poll(() => mockCalls(page, "/gaps")).toBeGreaterThanOrEqual(1);
    const before = await mockCalls(page, "/gaps");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible({ timeout: 2_000 });
    expect(await mockCalls(page, "/gaps")).toBe(before);
  });
});

test.describe("icons", () => {
  test("the three destination cards use inline SVG line icons, decorative, and no emoji", async ({ page }) => {
    await page.goto("/");
    for (const name of ["inbox", "smartphone", "trending-up"]) {
      const icon = page.locator(`svg[data-icon="${name}"]`);
      await expect(icon).toHaveCount(1);
      await expect(icon).toHaveAttribute("aria-hidden", "true");
      await expect(icon).toHaveAttribute("stroke", "currentColor");
    }
    const text = await page.locator("main").innerText();
    expect(text).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u);
  });

  test("every svg icon on the page is aria-hidden, after the beat opens", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByTestId("beat-panel").waitFor();
    const bad = await page.evaluate(() =>
      Array.from(document.querySelectorAll("svg[data-icon]")).filter((s) => s.getAttribute("aria-hidden") !== "true").length,
    );
    expect(bad).toBe(0);
    await expect(page.locator('svg[data-icon="shield-check"]')).toHaveCount(1); // the checks line
  });

  test("the phone view uses the camera and mic icons, not emoji", async ({ page }) => {
    await page.goto("/phone");
    await expect(page.locator('svg[data-icon="camera"]')).toHaveAttribute("aria-hidden", "true");
    await expect(page.locator('svg[data-icon="mic"]')).toHaveAttribute("aria-hidden", "true");
    expect(await page.locator("main").innerText()).not.toMatch(/[\u{1F300}-\u{1FAFF}]/u);
  });
});
