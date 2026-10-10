import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson } from "./helpers";

// The Desk on a phone (< 768 px): two screens, the inbox and one play's detail, with a "Back to
// inbox" bar and the browser's Back button both returning to the inbox. Pixel 7 project.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const inbox = (page: Page) => page.getByLabel("Play inbox");
const chipsRow = (page: Page) => inbox(page).getByRole("button", { name: /Masala Chips 200G/ }).first();
const hash = (page: Page) => page.evaluate(() => window.location.hash);

test.describe("desk on a phone: the inbox first", () => {
  test("the inbox is the first screen; the detail is not on it", async ({ page }) => {
    await page.goto("/desk");
    await expect(page.getByTestId("inbox-heading")).toBeVisible();
    await expect(inbox(page)).toBeVisible();
    await expect(page.getByTestId("play-detail")).toBeHidden();
    await expect(page.getByTestId("desk-back")).toBeHidden();
    await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0); // not on this screen at all
  });

  test("the heading says Top N of M gaps by rupees at stake, from the data already loaded", async ({ page }) => {
    await page.goto("/desk");
    // 7 plays in the mock inbox, 16 gaps in the portfolio
    await expect(page.getByTestId("inbox-heading")).toHaveText("Top 7 of 16 gaps by rupees at stake");
  });

  test("the 'of M' is left out when the gap list is unavailable", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(page, beatHandlers({ "/gaps": okJson([]) }));
    await page.goto("/desk");
    await expect(page.getByTestId("inbox-heading")).toHaveText("Top 7 gaps by rupees at stake");
  });

  test("each row shows a status chip, a relative deadline chip and the rupees at stake", async ({ page }) => {
    await page.goto("/desk");
    const chips = page.getByTestId("inbox-row").filter({ hasText: "Masala Chips 200G" });
    await expect(chips.getByTestId("inbox-status")).toHaveText("Proposed");
    await expect(chips.getByTestId("inbox-due")).toHaveText("in 6 days");
    await expect(chips.getByTestId("inbox-due")).toHaveAttribute("title", "Fri 18 Sep 2026");
    await expect(chips).toContainText("₹9,200 at stake");
    const tea = page.getByTestId("inbox-row").filter({ hasText: "Darjeeling Tea 100G" });
    await expect(tea.getByTestId("inbox-due")).toHaveText("in 24 days");
    // first row is the biggest gap
    await expect(page.getByTestId("inbox-row").first()).toContainText("Darjeeling Tea 100G");
    await expect(page.getByTestId("inbox-row").first()).toContainText("₹35,020 at stake");
    // a far deadline is a plain date, as everywhere else
    await expect(page.getByTestId("inbox-row").filter({ hasText: "Quinoa 500G" }).getByTestId("inbox-due")).toHaveText("9 Jul 2027");
  });

  test("a deadline in the past reads '6 days ago'", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const gaps = mockFixture("gaps").map((g: { gap_id: string; deadline_date: string }) =>
      g.gap_id === "gap_chips_ds07" ? { ...g, deadline_date: "2026-09-06" } : g,
    );
    await fakeApi(page, beatHandlers({ "/gaps": okJson(gaps) }));
    await page.goto("/desk");
    const due = page.getByTestId("inbox-row").filter({ hasText: "Masala Chips 200G" }).getByTestId("inbox-due");
    await expect(due).toHaveText("6 days ago");
  });
});

test.describe("desk on a phone: the detail screen", () => {
  test("tapping a play opens its detail with a Back to inbox bar; Approve is on the first screen, not past the inbox", async ({ page }) => {
    await page.goto("/desk");
    await chipsRow(page).click();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(inbox(page)).toBeHidden();
    await expect(page.getByRole("button", { name: "Back to inbox" })).toBeVisible();
    expect(await hash(page)).toBe("#play=play_chips_ds07_v1");
    expect(await page.evaluate(() => window.scrollY)).toBeLessThan(5);
    const approve = page.getByTestId("play-detail").getByRole("button", { name: "Approve" });
    await expect(approve).toBeInViewport({ ratio: 1 });
    expect((await approve.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  });

  test("Back to inbox returns to the inbox, with the play still marked", async ({ page }) => {
    await page.goto("/desk");
    await chipsRow(page).click();
    await page.getByRole("button", { name: "Back to inbox" }).click();
    await expect(inbox(page)).toBeVisible();
    await expect(page.getByTestId("play-detail")).toBeHidden();
    expect(await hash(page)).toBe("");
    await expect(chipsRow(page)).toHaveAttribute("aria-current", "true");
  });

  test("the browser's Back button does the same, and Forward goes to the detail again", async ({ page }) => {
    await page.goto("/desk");
    await chipsRow(page).click();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await page.goBack();
    await expect(inbox(page)).toBeVisible();
    await expect(page.getByTestId("play-detail")).toBeHidden();
    await page.goForward();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(inbox(page)).toBeHidden();
  });

  test("a link to #play=<id> opens that play's detail", async ({ page }) => {
    await page.goto("/desk#play=play_chips_ds07_v1");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(page.getByTestId("play-ids")).toContainText("play_chips_ds07_v1");
    await expect(page.getByRole("button", { name: "Back to inbox" })).toBeVisible();
    await page.getByRole("button", { name: "Back to inbox" }).click();
    await expect(inbox(page)).toBeVisible();
  });

  test("Approve works from the detail screen, and the inbox row then says Approved", async ({ page }) => {
    await page.goto("/desk");
    await chipsRow(page).click();
    const card = page.getByTestId("play-detail");
    await card.getByRole("button", { name: "Approve" }).click();
    await card.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await page.getByRole("button", { name: "Back to inbox" }).click();
    // the list was read before the approval; the chip follows after a reload of the page's data
    await page.reload();
    await expect(page.getByTestId("inbox-row").filter({ hasText: "Masala Chips 200G" }).getByTestId("inbox-status")).toHaveText("Approved");
  });
});

test.describe("desk on a phone: repeated live runs collapse into one row", () => {
  test("Plan live adds one run for the gap: one row with the newest run and '+1 earlier run' in Details", async ({ page }) => {
    await page.goto("/desk");
    const teaRows = page.locator('[data-testid="inbox-row"][data-gap="gap_tea_ds04"]');
    await page.getByTestId("inbox-row").filter({ hasText: "Darjeeling Tea 100G" }).getByRole("button").first().click();
    await page.getByTestId("plan-live").click();
    await page.getByRole("heading", { name: "Re-plan result" }).waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: "Back to inbox" }).click();

    await expect(teaRows).toHaveCount(1); // not two Tea rows
    await expect(teaRows.locator(".inbox__live")).toHaveText("Live run");
    const earlier = teaRows.getByTestId("earlier-runs");
    await expect(earlier.locator("summary")).toContainText("+1 earlier run");
    await expect(earlier.getByRole("button")).toBeHidden(); // closed by default
    await earlier.locator("summary").click();
    await expect(earlier.getByRole("button")).toHaveCount(1);
    await expect(earlier.getByRole("button")).toContainText("play_tea_ds04_v1");

    // the earlier run can be opened from there
    await earlier.getByRole("button").click();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(page.getByTestId("play-ids")).toContainText("play_tea_ds04_v1");
  });
});

test.describe("desk on a phone: no horizontal overflow at 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("inbox, detail and a play with two runs", async ({ page }) => {
    await page.goto("/desk");
    await page.getByTestId("inbox-heading").waitFor();
    await assertNoHorizontalOverflow(page);
    await chipsRow(page).click();
    await page.getByTestId("play-detail").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByTestId("play-detail").getByTestId("guardrail-summary").click();
    await assertNoHorizontalOverflow(page);
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`desk on a phone: axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    test("inbox and detail screens", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/desk");
      await page.getByTestId("inbox-heading").waitFor();
      await page.waitForTimeout(300);
      let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "inbox: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
      await chipsRow(page).click();
      await page.getByTestId("play-detail").waitFor();
      await page.getByTestId("card-details").locator("summary").click();
      await page.waitForTimeout(300);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "detail: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  });
}
