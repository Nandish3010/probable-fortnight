import { test, expect } from "@playwright/test";
import { clearMockFaults, injectMockFaults, mockCalls } from "./helpers";

// The 60-second beat opens on HERO_GAP_ID (app/page.tsx), currently the Darjeeling Tea lot at
// Dark store 4. Nothing below hard-codes that gap except these constants, so a change of hero is
// one constant in page.tsx plus these three lines.
const HERO = { name: "Darjeeling Tea 100G", atStake: "₹35,020", skuId: "SKU-DARJEELING-TEA-100G" };

test.describe("judge-mode landing", () => {
  test("paints with no console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("60-second beat: gap card, approve, chart", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();

    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("why-now")).toContainText(HERO.atStake);

    await page.getByRole("button", { name: "Approve" }).click();

    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("writeoff-line")).toContainText("→", { timeout: 30_000 });
  });

  test("the beat opens on the hero gap, in plain language, with the raw ids one click away", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const beat = page.getByTestId("beat-panel");
    await expect(beat.getByRole("heading", { name: HERO.name })).toBeVisible();
    await expect(beat.getByText("Dark store 4 · Online sell-by breach")).toBeVisible();
    await expect(beat.getByRole("heading", { name: "What Taal will do" })).toBeVisible();
    await expect(beat.getByTestId("plan-sentence")).toContainText("Transfer stock, then nudge customers.");
    // the gap-type and mechanic ids are not the visible text
    await expect(beat.getByText("online_sellby_breach").locator("visible=true")).toHaveCount(0);
    await expect(beat.getByText("transfer_plus_nudge").locator("visible=true")).toHaveCount(0);
    // ... but they are reachable inside the card's Details
    await beat.getByTestId("card-details").locator("summary").click();
    await expect(beat.getByTestId("gap-ids")).toContainText(HERO.skuId);
    await expect(beat.getByTestId("gap-ids")).toContainText("gap_tea_ds04");
    await expect(beat.getByTestId("play-ids")).toContainText("transfer_plus_nudge");
    // the card says where the play came from (a scripted fixture here), not "recorded" by default
    await expect(beat.getByTestId("play-card").locator(".badge--scripted")).toBeVisible();
  });

  test("the gap card states the countdown once and explains the sell-by rule only for a sell-by gap", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const card = page.locator(".gap-card");
    await expect(card.locator(".gap-card__stats .stat__value").nth(2)).toHaveText("24d");
    const rule = card.locator(".gap-card__rule");
    await expect(rule).toHaveCount(1);
    await expect(rule).toContainText("Online sell-by rule v1-either");
    await expect(rule).not.toContainText("24 days"); // the countdown is not repeated
  });

  test("approve result: one audience chain, the canonical figure and an honest what-if caption", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByRole("button", { name: "Approve" }).click();
    const result = page.getByTestId("approve-result");
    await expect(result).toBeVisible({ timeout: 30_000 });

    // The mock approve for the Tea play (lib/mockData.ts): 323 consented, 291 treated, 32 holdout
    await expect(result.getByTestId("audience-chain")).toHaveText("323 consented: 291 treated and 32 holdout");
    await expect(result.locator(".chip")).toHaveCount(0); // the chain replaces the old holdout/treated chip

    // Tea: a transfer play, so recovered = margin (7,498) = waste avoided 7,704 minus transfer cost 206
    const figure = result.getByTestId("approve-recovered");
    await expect(figure).toContainText("Recovered vs doing nothing ₹7,498");
    await expect(figure.getByTestId("approve-recovered-parts")).toContainText("waste avoided (at cost) ₹7,704 minus transfer cost ₹206");

    await expect(result.getByTestId("writeoff-caption")).toContainText(
      "What-if forecast using the past promo lift. Not the play's own estimate.",
    );
  });

  test("Approve cannot double-submit: two fast clicks send one request", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const approve = page.getByRole("button", { name: "Approve" });
    await expect(approve).toBeVisible();
    // dispatch two clicks in the same tick, before React can re-render the button as disabled
    await approve.evaluate((el) => {
      (el as HTMLButtonElement).click();
      (el as HTMLButtonElement).click();
    });
    await expect(page.getByTestId("approve-result")).toBeVisible({ timeout: 30_000 });
    expect(await mockCalls(page, "/approve")).toBe(1);
  });

  test("while approving, the button is disabled and busy", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByRole("button", { name: "Approve" }).click();
    const busy = page.getByRole("button", { name: "Approving…" });
    await expect(busy).toBeDisabled();
    await expect(busy).toHaveAttribute("aria-busy", "true");
  });

  test("chat as Meena responds within 6s", async ({ page }) => {
    await page.goto("/");
    const log = page.getByTestId("chat-log").first();
    await page.getByRole("button", { name: "Send" }).first().click();

    await expect(log).toContainText(/Best before|ಬಳಕೆಗೆ/, { timeout: 6_000 });
  });
});

test.describe("landing: a failing service never leaves a spinner", () => {
  test("the beat shows a plain-language card with Retry and Show recorded, and Retry recovers", async ({ page }) => {
    // Every /gaps call fails (the page prefetches the beat on load, so a counted fault would be
    // spent before the click); the fault is cleared before Retry.
    await injectMockFaults(page, { "/gaps": { kind: "network" } });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card).toHaveAttribute("role", "alert");
    await expect(card).toContainText("Can't reach the Taal service");
    await expect(card).toContainText("The demo server isn't answering. This usually clears in a minute.");
    await expect(page.getByText("Loading gap and play…")).toHaveCount(0);

    await clearMockFaults(page);
    await card.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("error-card")).toHaveCount(0);
  });

  test("Show recorded result opens the shipped copy and labels it REPLAY", async ({ page }) => {
    await injectMockFaults(page, { "/gaps": { kind: "http" } });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toContainText("Something went wrong");
    await card.getByRole("button", { name: "Show recorded result" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("recorded-note")).toContainText("REPLAY");
    await expect(page.getByTestId("beat-panel").getByRole("heading", { name: HERO.name })).toBeVisible();
  });
});
