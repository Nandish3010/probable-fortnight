import { test, expect } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";

test.describe("outcomes: measure button", () => {
  test("Run Measure is clickable and reports a summary", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/outcomes");
    await expect(page.getByRole("heading", { name: "Outcomes" })).toBeVisible();
    await expect(page.getByText("Masala Chips 200G").first()).toBeVisible();

    await page.getByRole("button", { name: "Run Measure" }).click();
    await expect(page.getByText(/plays? joined against orders/)).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test.describe("outcomes: estimator prior on the featured play", () => {
  test("the prior update line shows on the featured card and survives Reset", async ({ page }) => {
    const line = /Estimator prior: Beta\(1,19\) → Beta\(17,326\) · SYNTHETIC orders/;
    await page.goto("/outcomes");
    const card = page.locator(".card", { hasText: "Worked example: Masala Chips 200G" });
    await expect(card.getByText(line)).toBeVisible();
    await expect(card.locator(".prior-update .badge--synthetic")).toHaveText("SYNTHETIC");

    await page.goto("/");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await expect(page.getByRole("button", { name: "Reset demo data" })).toBeEnabled();
    await page.goto("/outcomes");
    await expect(page.locator(".card", { hasText: "Worked example: Masala Chips 200G" }).getByText(line)).toBeVisible();
  });
});

test.describe("outcomes: honest wording of a lift", () => {
  test("the lift is a response-rate difference in points; an interval across zero is badged Inconclusive and the CEO number is withheld", async ({ page }) => {
    await page.goto("/outcomes");
    const row = page.locator(".outcomes-table tbody tr").filter({ hasText: "Masala Chips 200G" });
    // mocks/outcomes.json carries lift_pp / ci_low_pp / ci_high_pp / inconclusive for this row
    await expect(row).toContainText("response-rate difference, +0.3 percentage points (95% CI -11.4 to +1.7 points)");
    const badge = row.getByTestId("inconclusive-badge");
    await expect(badge).toBeVisible();
    await expect(badge).toHaveAttribute("title", "The interval crosses zero or too few customers responded");
    await expect(row.getByTestId("ceo-withheld")).toHaveText("withheld: inconclusive");
    await expect(row.locator(".ceo-number")).toHaveCount(0);
  });

  test("every measured row of the regenerated outcomes carries the API's *_pp fields and flag, and the badge follows the flag", async ({ page }) => {
    await page.goto("/outcomes");
    const row = page.locator(".outcomes-table tbody tr").filter({ hasText: "Kaju Katli 250G" });
    await expect(row).toContainText("response-rate difference, 0.0 percentage points (95% CI -12.1 to +1.3 points)");
    await expect(row.getByTestId("inconclusive-badge")).toBeVisible();
  });

  test("the worked example's lift line uses the same wording", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.locator(".prior-update")).toContainText(
      "response-rate difference, +1.5 percentage points (95% CI -12.4 to +5.6 points)",
    );
  });

  test("the worked example shows the canonical figure and gap types use the shared label map", async ({ page }) => {
    await page.goto("/outcomes");
    const card = page.locator(".card", { hasText: "Worked example: Masala Chips 200G" });
    await expect(card.getByTestId("recovered-figure")).toContainText("Recovered vs doing nothing ₹732");
    await expect(page.locator(".portfolio-card__table")).toContainText("Online sell-by breach");
  });
});


/** A browser whose crumbs say the visitor approved the chips play, which the mock outcomes have measured. */
async function seedApprovedChips(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("taal_visitor", "v-outcomes");
    window.localStorage.setItem(
      "taal_progress:v-outcomes",
      JSON.stringify({
        spot: true,
        plan: true,
        offer: true,
        approved: [{ play_id: "play_chips_ds07_v1", gap_id: "gap_chips_ds07", at: "2026-09-12T03:30:00Z" }],
      }),
    );
  });
}

test.describe("outcomes: summary card first", () => {
  test("without an approval the page opens on the empty state with Run Measure as the primary button", async ({ page }) => {
    await page.goto("/outcomes");
    const summary = page.getByTestId("outcome-summary");
    await expect(summary).toBeVisible();
    await expect(summary.getByTestId("summary-empty")).toContainText("Nothing is measured in your session yet. Approve a play, then Run Measure.");
    await expect(summary.getByRole("button", { name: "Run Measure" })).toHaveClass(/button-primary/);
    await expect(summary).toContainText("Nothing in your session is measured until you click Run Measure.");
    // it is the first card: above the portfolio block, which keeps its SYNTHETIC badge
    const order = await page.locator("main > section, main > .card").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.testid ?? ""));
    expect(order.indexOf("outcome-summary")).toBeLessThan(order.indexOf("portfolio-card"));
    await expect(page.getByTestId("portfolio-card").locator(".badge--synthetic")).toHaveText(/SYNTHETIC/);
  });

  test("with an approved, measured play the card leads with the difference in points, its range, the badge and the withheld CEO number", async ({ page }) => {
    await seedApprovedChips(page);
    await page.goto("/outcomes");
    const summary = page.getByTestId("outcome-summary");
    await expect(summary.getByTestId("summary-difference")).toContainText("+0.3 points");
    await expect(summary.getByTestId("summary-difference")).toContainText("95% CI -11.4 to +1.7 points");
    await expect(summary.getByTestId("inconclusive-badge")).toBeVisible();
    await expect(summary.getByTestId("summary-ceo")).toContainText("withheld: inconclusive");
    await expect(summary).not.toContainText("%-");
  });

  test("the worked example says it is seeded and not the visitor's approval; the sentence about running automatically is reworded", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByTestId("seeded-example-note")).toHaveText("Seeded example, computed at build time. Not your approval.");
    await expect(page.locator("main")).not.toContainText("never run automatically");
  });

  test("no code-ish strings on the surface: commands, docs paths and run ids live inside Details", async ({ page }) => {
    await page.goto("/outcomes");
    const surface = await page.locator("main").evaluate((main) => {
      const clone = main.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("details").forEach((d) => d.querySelectorAll(":scope > div").forEach((b) => b.remove()));
      return clone.innerText;
    });
    for (const bad of ["python -m", "docs/", "sense_20", "Looker (n/a)", "took 0.0"]) expect(surface).not.toContain(bad);
    await expect(page.getByTestId("portfolio-details")).toContainText("jobs.portfolio");
    await expect(page.getByRole("button", { name: /Looker/ })).toHaveCount(0);
  });

  test("tiles use plain labels and Indian digit grouping", async ({ page }) => {
    await page.goto("/outcomes");
    const card = page.getByTestId("portfolio-card");
    await expect(card).toContainText("Total at stake");
    await expect(card).toContainText("Expected recovered");
    await expect(card).toContainText("Plans drafted");
    await expect(card).toContainText("₹17,95,464");
    // no thousands-style grouping of a six-figure number inside the card
    const text = await card.innerText();
    expect(text).not.toMatch(/\d{1,3}(,\d{3}){2,}/);
  });
});

test.describe("outcomes: phone", () => {
  test.use({ viewport: { width: 360, height: 800 } });
  test("the table stacks into cards at 360 px: no sideways scroll and the CEO number is on screen", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.locator(".outcomes-table tbody tr").first()).toBeVisible();
    await assertNoHorizontalOverflow(page);
    const row = page.locator(".outcomes-table tbody tr").filter({ hasText: "Masala Chips 200G" });
    const cell = row.locator("td[data-label='CEO number']");
    await cell.scrollIntoViewIfNeeded();
    const box = (await cell.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(360);
    await expect(cell).toBeInViewport();
  });
});
