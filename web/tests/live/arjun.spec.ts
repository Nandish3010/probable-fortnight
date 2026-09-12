import { test, expect } from "@playwright/test";
import { asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot } from "./helpers";

test.describe("Arjun: Play Desk", () => {
  test("inbox, play card, trace, why, edit, approve, policy re-plan", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-arjun");
    await page.goto("/desk");
    await expect(page.getByRole("heading", { name: "Play Desk" })).toBeVisible();
    const inbox = page.getByLabel("Play inbox");
    await expect(inbox.locator(".inbox__item").first()).toBeVisible();
    await shot(page, "arjun-01-inbox");

    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    for (const h of ["Target", "Mechanic", "Audience", "Copy", "Expected outcome", "Counterfactuals", "Guardrails", "Rationale (editable)", "Holdout fraction", "Trace"]) {
      await expect(card.getByRole("heading", { name: h })).toBeVisible();
    }
    await expect(card.getByText(/est-v1/).first()).toBeVisible();
    await expect(card.getByText(/margin_floor/).first()).toBeVisible();
    await expect(card.getByText("9,200").first()).toBeVisible();
    await shot(page, "arjun-02-play-card");

    await card.getByRole("button", { name: "Why this play?" }).click();
    await expect(card.getByText(/coupon/).first()).toBeVisible();
    await expect(card.getByText(/margin floor|margin_floor/).first()).toBeVisible();
    await shot(page, "arjun-03-why");

    // trace shows the revision
    await expect(card.getByText(/Guardrail failed: margin_floor/).first()).toBeVisible();
    await card.getByRole("button", { name: /Replay at 4x/ }).click();
    await expect(card.getByRole("button", { name: /Replay/ })).toBeVisible();

    // edit the rationale, then approve: the play records the edit
    const ta = card.locator("textarea").first();
    await ta.fill("Approved for the Friday rush. 368 units at risk, ₹9200 write-off if we do nothing.");
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await shot(page, "arjun-04-approved");

    // policy beat on the tea play
    await inbox.getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    await expect(card.getByText(/transfer_plus_nudge/).first()).toBeVisible();
    const policy = card.locator("textarea").last();
    const text = await policy.inputValue();
    await policy.fill(text.replace("; prefer transfers for premium tea", ""));
    await card.getByRole("button", { name: /Change policy/ }).click();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 60_000 });
    await expect(card.getByText(/v2/).first()).toBeVisible();
    await shot(page, "arjun-05-replan");
    await expectNoConsoleErrors(errors);
  });
});
