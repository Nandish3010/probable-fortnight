import { expect, test } from "@playwright/test";
import { assertNoHorizontalOverflow, openBeat } from "./helpers";

// The page never scrolls sideways at 360 px (a small Android phone). One assertion per state, so
// a state that overflows is named in the report. States known to overflow today are test.fixme
// with the task that fixes them (ux_plan.md section 7).
test.use({ viewport: { width: 360, height: 800 } });

test.describe("no horizontal overflow at 360 px", () => {
  test("landing", async ({ page }) => {
    await page.goto("/");
    await assertNoHorizontalOverflow(page);
  });

  // At 360 px the landing is the feed of the top decisions (components/DecisionFeed.tsx).
  test("landing, the feed loaded", async ({ page }) => {
    await openBeat(page);
    await page.getByTestId("feed-item-3").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  // Was a known overflow (525 px wide): the LIVE/REPLAY badge in the Approve result held
  // "model · live · latency · run id" on one nowrap line and stretched its card. Badges now wrap.
  test("landing, after Approve (the result and Next decision)", async ({ page }) => {
    const card = await openBeat(page);
    await card.getByRole("button", { name: "Approve" }).click();
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await page.getByTestId("feed-next").first().waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("landing, the second decision approved too", async ({ page }) => {
    await openBeat(page);
    const second = page.getByTestId("feed-item-2");
    await second.getByRole("button", { name: "Approve" }).click();
    await second.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await assertNoHorizontalOverflow(page);
  });

  test("landing, feed with Details, the legend and the guardrail list open", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("state-legend").locator("summary").click();
    const card = await openBeat(page, { goto: false });
    await card.getByTestId("guardrail-summary").click();
    await card.getByTestId("card-details").locator("summary").click();
    await assertNoHorizontalOverflow(page);
  });

  test("landing, the feed failed (error card)", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/gaps": { kind: "network" } })));
    await page.goto("/");
    await page.getByTestId("error-card").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("landing, Reset dialog open", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByRole("dialog").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("desk, the inbox screen", async ({ page }) => {
    await page.goto("/desk");
    await page.getByTestId("inbox-heading").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("desk, the detail screen with guardrails open", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await page.getByTestId("play-detail").waitFor();
    await page.getByTestId("guardrail-summary").click();
    await assertNoHorizontalOverflow(page);
  });

  test("desk, a play open with Details open, then after Approve", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("card-details").locator("summary").click();
    await assertNoHorizontalOverflow(page);
    await card.getByRole("button", { name: "Approve" }).click();
    await card.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await assertNoHorizontalOverflow(page);
  });

  test("desk, the Tea (transfer) play open", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    await page.getByTestId("play-detail").waitFor();
    await page.getByTestId("guardrail-summary").click();
    await assertNoHorizontalOverflow(page);
  });

  test("desk, a gap with two runs (earlier runs open)", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    await page.getByTestId("plan-live").click();
    await page.getByRole("heading", { name: "Re-plan result" }).waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: "Back to inbox" }).click();
    await page.getByTestId("earlier-runs").locator("summary").click();
    await assertNoHorizontalOverflow(page);
  });

  test("phone", async ({ page }) => {
    await page.goto("/phone");
    await assertNoHorizontalOverflow(page);
  });

  test("phone, after capture (photo read, rows in the table)", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 6" }).click();
    await page.getByTestId("intake-table").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("phone, after Approve", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await page.getByTestId("intake-table").waitFor();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await page.getByTestId("why-now").waitFor();
    await page.getByRole("button", { name: "Approve" }).click();
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await assertNoHorizontalOverflow(page);
  });

  test("phone, after a photo and Confirm rows", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await page.getByTestId("intake-table").waitFor();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await page.getByTestId("why-now").waitFor();
    await assertNoHorizontalOverflow(page);
  });
});

test.describe("no horizontal overflow at 360 px: the stepper and the restarted banner", () => {
  test("every step label fits inside its column", async ({ page }) => {
    await page.goto("/");
    await assertNoHorizontalOverflow(page);
    const clipped = await page.getByTestId("stepper").evaluate((nav) =>
      Array.from(nav.querySelectorAll<HTMLElement>('li [data-part="label"], li [data-part="dot"]')).filter((el) => el.scrollWidth > el.clientWidth + 0.5).length,
    );
    expect(clipped).toBe(0);
  });

  test("with the sandbox-restarted banner showing", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("taal_visitor", "v-overflow");
      window.localStorage.setItem(
        "taal_progress:v-overflow",
        JSON.stringify({ spot: true, plan: true, offer: false, approved: [{ play_id: "play_tea_ds04_v1", gap_id: "gap_tea_ds04", at: "2026-09-12T03:30:00Z" }] }),
      );
    });
    await page.goto("/");
    await page.getByTestId("sandbox-banner").waitFor();
    await assertNoHorizontalOverflow(page);
  });
});
