import { test, expect, type Page } from "@playwright/test";
import { assertNoHorizontalOverflow, openBeat } from "./helpers";

// The one decision card (components/PlayCard.tsx) in its three modes. Mock mode: the landing hero
// gap is the Darjeeling Tea lot at Dark store 4 (a transfer play); the Desk opens the Chips play.

/** Document position of each child of the card, to assert the element order. */
async function orderOf(page: Page, root: string, selectors: string[]): Promise<number[]> {
  return page.evaluate(
    ([rootSel, sels]) => {
      const rootEl = document.querySelector(rootSel as string)!;
      return (sels as string[]).map((s) => {
        const el = rootEl.querySelector(s);
        if (!el) return -1;
        return Array.from(rootEl.querySelectorAll("*")).indexOf(el);
      });
    },
    [root, selectors],
  );
}

test.describe("PlayCard: hero mode (landing)", () => {
  test("one element order: eyebrow, why now, figure, bars, plan, checks, Approve, Details", async ({ page }) => {
    const beat = await openBeat(page);
    const card = beat.getByTestId("play-card");
    await expect(card).toHaveAttribute("data-mode", "hero");

    const pos = await orderOf(page, '[data-testid="play-card"]', [
      "h3", // eyebrow
      '[data-testid="why-now"]',
      '[data-testid="recovered-figure"]',
      ".counterfactuals__row",
      '[data-testid="comparison-line"]',
      '[data-testid="plan-sentence"]',
      '[data-testid="card-checks"]',
      '[data-testid="decision"]',
      '[data-testid="card-details"]',
    ]);
    expect(pos.every((p) => p >= 0), `an element is missing: ${pos}`).toBe(true);
    expect([...pos].sort((a, b) => a - b)).toEqual(pos);
  });

  test("the headline figure, its two parts, the honesty line and the three bars", async ({ page }) => {
    const beat = await openBeat(page);
    // Tea is a transfer play: waste avoided minus transfer cost
    await expect(beat.getByTestId("recovered-figure")).toContainText("Recovered vs doing nothing ₹7,498");
    await expect(beat.getByTestId("recovered-figure-parts")).toContainText("waste avoided (at cost) ₹7,704 minus transfer cost ₹206");
    await expect(beat.getByTestId("honesty-line")).toContainText("not a measurement");
    await expect(beat.locator(".counterfactuals__row")).toHaveCount(3);
    await expect(beat.locator(".counterfactuals__row--play")).toHaveCount(1);
    await expect(beat.getByTestId("comparison-line")).toHaveText("Beats a blanket 20% markdown by ₹4,493");
    // computed from the play's own audience and holdout fraction, said as an estimate
    await expect(beat.getByTestId("plan-sentence")).toContainText("About 291 of 323 consented customers get the offer; about 32 are held back");
  });

  test("Approve is the only Approve button, reachable before Details, and the card keeps Details collapsed", async ({ page }) => {
    const beat = await openBeat(page);
    await expect(beat.getByRole("button", { name: "Approve" })).toHaveCount(1);
    await expect(beat.getByTestId("card-details")).not.toHaveAttribute("open", "");
    // the FSSAI wording lives in Details, softened; it is not in the hero line
    await beat.getByTestId("card-details").locator("summary").click();
    await expect(beat.getByTestId("card-details")).toContainText("Sold within FSSAI's online sell-by advisory for e-commerce food sellers");
    await expect(page.getByRole("heading", { level: 1 })).not.toContainText("FSSAI");
  });

  test("after Approve the card shows the result in the same place and the old sticky row is released", async ({ page }) => {
    const beat = await openBeat(page);
    await expect(beat.getByTestId("decision")).toHaveAttribute("data-sticky", "on");
    await beat.getByRole("button", { name: "Approve" }).click();
    await expect(beat.getByTestId("approve-result")).toBeVisible({ timeout: 30_000 });
    await expect(beat.getByTestId("decision")).toHaveAttribute("data-sticky", "off");
    // the result's own figure is the same canonical figure
    await expect(beat.getByTestId("approve-recovered")).toContainText("Recovered vs doing nothing ₹7,498");
  });
});

test.describe("PlayCard: detail mode (Desk)", () => {
  async function openChips(page: Page) {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    return page.getByTestId("play-detail");
  }

  test("renders the same card in detail mode, with the Desk's holdout control and editor in it", async ({ page }) => {
    const card = await openChips(page);
    const pc = card.getByTestId("play-card");
    await expect(pc).toHaveAttribute("data-mode", "detail");
    await expect(pc.getByTestId("why-now")).toBeVisible();
    await expect(pc.getByTestId("recovered-figure")).toHaveCount(1);
    await expect(pc.getByLabel("Holdout fraction")).toBeVisible();
    // the editable rationale is inside Details, with the line that says edits travel with Approve
    await pc.getByTestId("card-details").locator("summary").click();
    await expect(pc.getByLabel("Rationale")).toBeVisible();
    await expect(pc.getByText("Edits are saved with the approval.")).toBeVisible();
    // Desk-only sections come after the decision, not before it
    await expect(card.locator(".trace-panel")).toBeVisible();
    await expect(card.locator(".policy-editor")).toBeVisible();
    const pos = await orderOf(page, '[data-testid="play-card"]', ['[data-testid="decision"]', ".trace-panel", ".policy-editor"]);
    expect(pos[0]).toBeGreaterThan(0);
    expect(pos[1]).toBeGreaterThan(pos[0]);
    expect(pos[2]).toBeGreaterThan(pos[1]);
  });

  test("the holdout slider changes the card's estimate", async ({ page }) => {
    const card = await openChips(page);
    await expect(card.getByTestId("plan-sentence")).toContainText("About 317 of 352 consented customers get the offer; about 35 are held back");
    await card.getByLabel("Holdout fraction").fill("0.5");
    await expect(card.getByTestId("plan-sentence")).toContainText("about 176 are held back");
  });

  test("a bar under the nav appears once Approve has scrolled out of view, and takes you back to it", async ({ page }) => {
    const card = await openChips(page);
    const bar = card.getByTestId("decision-bar");
    await expect(bar).toHaveCount(0);

    // scroll past the decision row (the Desk's trace and policy sections are long)
    const decision = card.getByTestId("decision");
    const bottom = await decision.evaluate((el) => el.getBoundingClientRect().bottom + window.scrollY);
    await page.evaluate((y) => window.scrollTo(0, y + 600), bottom);
    await expect(bar).toBeVisible();
    await expect(bar).toContainText("Recovered vs doing nothing ₹732");
    // the bar sits under the sticky nav and inside the viewport
    const box = (await bar.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeLessThan(120);

    // there is still exactly one Approve button on the page
    await expect(card.getByRole("button", { name: "Approve" })).toHaveCount(1);

    await bar.getByRole("button", { name: "Go to decision" }).click();
    await expect(card.getByRole("button", { name: "Approve" })).toBeFocused();
    await expect(card.getByRole("button", { name: "Approve" })).toBeInViewport();
    await expect(bar).toHaveCount(0);

    // back at the top the bar is gone too
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(bar).toHaveCount(0);
  });
});

test.describe("PlayCard: all three modes side by side (mock-mode preview route)", () => {
  test("hero, detail and feed render the same content; feed is the compact layout", async ({ page }) => {
    await page.goto("/dev/play-card");
    for (const mode of ["hero", "detail", "feed"]) {
      const card = page.getByTestId(`play-card-${mode}`);
      await expect(card).toHaveAttribute("data-mode", mode);
      await expect(card.getByTestId("why-now")).toBeVisible();
      await expect(card.getByTestId("recovered-figure")).toBeVisible();
      await expect(card.locator(".counterfactuals__row")).toHaveCount(3);
      await expect(card.getByRole("button", { name: "Approve" })).toBeVisible();
      await expect(card.getByTestId("card-details")).toBeVisible();
    }
    // the same text in every mode
    const texts = await Promise.all(
      ["hero", "detail", "feed"].map((m) => page.getByTestId(`play-card-${m}`).getByTestId("why-now").innerText()),
    );
    expect(new Set(texts).size).toBe(1);
    // feed is capped at 480 px wide
    const feedBox = (await page.getByTestId("play-card-feed").boundingBox())!;
    expect(feedBox.width).toBeLessThanOrEqual(480);
  });
});

test.describe("PlayCard: sticky Approve on a phone (390 x 844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the Approve row is pinned to the bottom of the screen while the card is on screen, with safe-area padding", async ({ page }) => {
    const beat = await openBeat(page);
    const decision = beat.getByTestId("decision");
    const style = await decision.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { position: cs.position, bottom: cs.bottom };
    });
    expect(style.position).toBe("sticky");
    expect(style.bottom).toBe("0px");
    // the safe-area inset is part of the bottom padding (0 in a desktop browser, so >= 12px)
    const pad = await decision.evaluate((el) => parseFloat(getComputedStyle(el).paddingBottom));
    expect(pad).toBeGreaterThanOrEqual(12);

    // Approve is inside the first screen without scrolling, though the card is much taller
    const approve = beat.getByRole("button", { name: "Approve" });
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(approve).toBeInViewport({ ratio: 1 });
    const cardBox = (await beat.getByTestId("feed-card-1").boundingBox())!;
    expect(cardBox.height).toBeGreaterThan(844);

    // ... and after scrolling a screen down it is still there
    await page.evaluate(() => window.scrollBy(0, 500));
    await expect(approve).toBeInViewport({ ratio: 1 });
    // 44 px tall at least, and the compact figure is shown beside it
    expect((await approve.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await expect(decision).toContainText("₹7,498");
    await assertNoHorizontalOverflow(page);
  });

  test("the Desk bar is not used on a phone (the sticky row does that job)", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(card.getByTestId("decision-bar")).toBeHidden();
    await expect(card.getByRole("button", { name: "Approve" })).toBeInViewport({ ratio: 1 });
  });
});
