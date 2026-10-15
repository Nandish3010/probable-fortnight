import { test, expect, type Page } from "@playwright/test";
import { approveSettled, assertNoHorizontalOverflow, mockCalls } from "./helpers";

// "Plan live" starts a new planner run on the selected play's gap. Run on a play the visitor has
// already approved, the new run becomes the newest play of that gap: the inbox row then reads
// "Proposed" and the approved play is demoted to "+1 earlier run", which looks like an un-approval.
// So on an approved play the button is off, with the reason beside it; on an unapproved play it works
// as before. (The API keeps the approved play and its offers: see coordination/ui-ux/final_push_audit.)

const REASON = "This play is approved. Reset the demo to plan it again.";

async function approveOnDesk(page: Page) {
  await page.goto("/desk");
  await expect(page.getByTestId("play-detail")).toBeVisible();
  await page.getByTestId("approve-button").click();
  await approveSettled(page);
}

for (const vp of [
  { name: "1280", width: 1280, height: 800 },
  { name: "375", width: 375, height: 812 },
] as const) {
  test.describe(`Plan live on an approved play at ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("after Approve the button is off, says why, and nothing is sent", async ({ page }) => {
      await page.goto("/desk");
      if (vp.width < 768) {
        await page.getByTestId("inbox-row").first().click();
      }
      await expect(page.getByTestId("play-detail")).toBeVisible();
      const button = page.getByTestId("plan-live");
      await expect(button).toBeEnabled(); // unapproved: Plan live works as before
      await expect(page.getByTestId("plan-live-reason")).toHaveCount(0);

      await page.getByTestId("approve-button").click();
      await approveSettled(page);

      await expect(button).toBeDisabled();
      await expect(button).toHaveText("Plan live");
      const reason = page.getByTestId("plan-live-reason");
      await expect(reason).toBeVisible();
      await expect(reason).toHaveText(REASON);
      await expect(button).toHaveAttribute("aria-describedby", (await reason.getAttribute("id")) ?? "missing");
      expect(await mockCalls(page, "/rerun")).toBe(0);
      await assertNoHorizontalOverflow(page);
    });
  });
}

test.describe("Plan live on an approved play, 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a reload keeps it off (the server reports the play as approved)", async ({ page }) => {
    await approveOnDesk(page);
    await page.reload();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(page.getByTestId("plan-live")).toBeDisabled();
    await expect(page.getByTestId("plan-live-reason")).toHaveText(REASON);
  });

  test("/desk?plan=live on an approved flagship does not start a run, and says why", async ({ page }) => {
    await approveOnDesk(page);
    await page.goto("/desk?plan=live");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(page.getByTestId("plan-live-reason")).toHaveText(REASON);
    await page.waitForTimeout(1200);
    expect(await mockCalls(page, "/rerun")).toBe(0);
    await expect(page.getByTestId("plan-live")).toBeDisabled();
  });

  test("an unapproved play still plans live (one run, as before)", async ({ page }) => {
    await page.goto("/desk");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await page.getByTestId("plan-live").click();
    await expect.poll(() => mockCalls(page, "/rerun")).toBe(1);
    await expect(page.getByTestId("plan-live-reason")).toHaveCount(0);
  });

  test("Reset demo data makes it available again", async ({ page }) => {
    await approveOnDesk(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText(/Reset done for visitor/)).toBeVisible();
    await page.goto("/desk");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(page.getByTestId("plan-live")).toBeEnabled();
    await expect(page.getByTestId("plan-live-reason")).toHaveCount(0);
  });
});
