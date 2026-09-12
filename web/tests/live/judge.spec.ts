import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

test.describe("judge: landing", () => {
  test("60-second beat, idempotent approve, chat, reset, isolation", async ({ page, browser }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-judge-a");
    await page.goto("/");
    await expect(page.getByText("Taal judge mode")).toBeVisible();
    await expect(page.getByText(/300 SKUs|SKUs/)).toBeVisible();
    await shot(page, "judge-01-landing");

    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const beat = page.getByTestId("beat-panel");
    await expect(beat.getByText("₹9,200")).toBeVisible();
    await expect(beat.getByText(/6 days/)).toBeVisible();
    await expect(beat.getByText(/v1-either/)).toBeVisible();
    await shot(page, "judge-02-gap-card");

    await beat.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("writeoff-line")).toContainText("→");
    await expect(page.getByText(/holdout/i).first()).toBeVisible();
    await expect(page.getByText(/refc_play_chips_ds07_v1/)).toBeVisible();
    await shot(page, "judge-03-approved-chart");

    // second approve must be idempotent
    const again = await page.request.post(`${API}/approve`, { headers: visitorHeaders("live-judge-a"), data: { play_id: "play_chips_ds07_v1" } });
    expect((await again.json()).note).toContain("already approved");

    // chat as Meena after approval: the offer arrives in Kannada with the best-before line
    const chat = page.getByTestId("chat-log");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(chat.getByText(/ಬಳಕೆಗೆ ಉತ್ತಮ|Best before/)).toBeVisible({ timeout: 15_000 });
    await expect(chat.getByRole("button", { name: /ಕಾರ್ಟ್|Add to cart/ })).toBeVisible();
    await shot(page, "judge-04-chat-offer");

    // isolation: another visitor still sees the play as proposed
    const other = await browser.newContext();
    const p2 = await other.newPage();
    await asVisitor(p2, "live-judge-b");
    const r = await p2.request.get(`${API}/plays/play_chips_ds07_v1`, { headers: visitorHeaders("live-judge-b") });
    expect((await r.json()).status).toBe("proposed");
    await other.close();

    // reset scoped to this visitor
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await expect(page.getByRole("button", { name: "Reset demo data" })).toBeEnabled();
    const after = await page.request.get(`${API}/plays/play_chips_ds07_v1`, { headers: visitorHeaders("live-judge-a") });
    expect((await after.json()).status).toBe("proposed");
    await shot(page, "judge-05-after-reset");
    await expectNoConsoleErrors(errors);
  });
});
