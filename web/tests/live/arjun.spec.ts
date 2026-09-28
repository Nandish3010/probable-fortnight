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
    // The flagship play is seeded from a real, committed Gemini recording (2026-09-28); the
    // model's own rejected alternative is a transfer, not a coupon (that was the old scripted
    // stub's story), rejected for negative expected margin.
    await expect(card.getByText(/transfer|negative expected margin/).first()).toBeVisible();
    await expect(card.getByText(/margin floor|margin_floor/).first()).toBeVisible();
    await shot(page, "arjun-03-why");

    // trace is readable to a judge: invocation_id visible, one line per tool call, the revision visible
    await expect(card.locator(".trace-panel__event").first()).toBeVisible();
    await expect((await card.locator(".trace-panel__event").count())).toBeGreaterThan(3);
    await expect(card.getByText(/^e-[0-9a-f-]+$/).first()).toBeVisible();
    // The real recorded run's own rejections were all cite_or_drop (an uncited number in the
    // rationale), not margin_floor -- that was the old scripted stub's story.
    await expect(card.getByText(/guardrail cite_or_drop|cite_or_drop/).first()).toBeVisible();

    // replay reproduces the same panel state as the live run, event for event (snapshot diff)
    const trace = card.locator(".trace-panel__list");
    const beforeReplay = await trace.innerText();
    // The real recorded run took 65 s wall time (7 iterations); at 4x replay that is ~16.2 s,
    // just over the old 15 s timeout sized for the much shorter scripted-stub trace.
    await card.getByRole("button", { name: /Replay at 4x/ }).click();
    await expect(card.getByRole("button", { name: "Replay at 4x" })).toBeVisible({ timeout: 25_000 });
    const afterReplay = await trace.innerText();
    expect(afterReplay).toBe(beforeReplay);

    // edit the rationale, then approve: the play records the edit
    const ta = card.locator("textarea").first();
    await ta.fill("Approved for the Friday rush. 368 units at risk, ₹9200 write-off if we do nothing.");
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    // ARIA status region for the result, screen-reader focus moved to its heading (ApprovePanel.tsx)
    const approveResult = page.getByTestId("approve-result");
    await expect(approveResult).toHaveAttribute("role", "status");
    await expect(approveResult.getByRole("heading", { name: /Approved/ })).toBeFocused();
    await shot(page, "arjun-04-approved");

    // policy beat on the tea play
    await inbox.getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    await expect(card.getByText(/transfer_plus_nudge/).first()).toBeVisible();
    const policy = card.locator("textarea").last();
    const text = await policy.inputValue();
    await policy.fill(text.replace("; prefer transfers for premium tea", ""));

    // POST /rerun now answers in 202 almost immediately and the planner keeps running after that
    // (services/api/main.py); a stub run can finish in a second or two, which would race past the
    // live-replan panel before this test could ever observe it. Delay the SSE stream's response
    // (fetch it for real, wait, then hand it back) so the panel is provably visible before the
    // eventual result, without fabricating any data -- every record the page receives is still the
    // real run's own trace.
    await page.route("**/events/*/stream", async (route) => {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ response });
    });

    await card.getByRole("button", { name: /Change policy/ }).click();
    await expect(page.getByTestId("live-replan")).toBeVisible();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 60_000 });
    await expect(card.getByText(/v2/).first()).toBeVisible();
    // ARIA status region for the re-plan result (web/app/desk/page.tsx)
    const replanResult = card.locator(".play-card__section").filter({ hasText: "Re-plan result" });
    await expect(replanResult).toHaveAttribute("role", "status");
    await shot(page, "arjun-05-replan");
    await expectNoConsoleErrors(errors);
  });
});
