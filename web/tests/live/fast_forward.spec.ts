import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

// E2 against the real API (stub model backend): "Fast-forward one day" places one order for the
// treated persona through the chat order flow and runs Measure, all in the visitor's sandbox.
test.describe("Management: fast-forward one day", () => {
  test("an approved play with nothing measured: one click orders, measures and shows the honest result", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-fast-forward";
    await asVisitor(page, vid);
    const h = visitorHeaders(vid);
    const approved = await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_chips_ds07_v1" } });
    expect(approved.ok()).toBeTruthy();

    await page.goto("/outcomes");
    const panel = page.getByTestId("fast-forward");
    await expect(panel).toBeVisible();
    await expect(panel.locator(".badge--synthetic")).toContainText("SYNTHETIC");
    await expect(page.getByTestId("outcome-summary")).toContainText("Nothing is measured in your session yet");
    await shot(page, "ff-01-before");

    await panel.getByRole("button", { name: "Fast-forward one day" }).click();
    await expect(page.getByTestId("fast-forward-steps")).toContainText("Placing Meena's order");
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 45_000 });

    const summary = page.getByTestId("outcome-summary");
    await expect(summary).toContainText("Response-rate difference");
    await expect(summary.getByTestId("ff-sample-size")).toContainText("1 treated customer ordered");
    await expect(summary.getByTestId("ff-explainer")).toHaveText(
      "One order is far too few to prove an effect. This shows the loop working; a pilot would supply the real numbers.",
    );
    await expect(summary.locator(".badge--synthetic").first()).toContainText("SYNTHETIC");
    await expect(panel.getByRole("button", { name: "Fast-forward one day" })).toBeDisabled();
    await expect(panel.getByTestId("fast-forward-already")).toHaveText("Already fast-forwarded in this session");
    await shot(page, "ff-02-after");

    const outs = await (await page.request.get(`${API}/outcomes`, { headers: h })).json();
    const chips = outs.find((o: { play_id: string }) => o.play_id === "play_chips_ds07_v1");
    expect(chips.status).toBe("measured");
    expect(chips.data_label).toBe("SYNTHETIC");
    expect(chips.treated.responders).toBe(1);
    await expect(summary.getByTestId("inconclusive-badge")).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test("the hero play (Tea): Ravi orders, and the stepper's Measure step turns done only now", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-fast-forward-tea";
    await asVisitor(page, vid);
    const h = visitorHeaders(vid);
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_tea_ds04_v1" } });

    await page.goto("/outcomes");
    const measure = page.getByTestId("stepper").locator('li[data-step="measure"]');
    await expect(page.getByTestId("fast-forward")).toBeVisible();
    await expect(measure).toHaveAttribute("data-done", "false"); // approved, but nothing of theirs is measured

    await page.getByRole("button", { name: "Fast-forward one day" }).click();
    await expect(page.getByTestId("fast-forward-steps")).toContainText("Placing Ravi's order");
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 45_000 });
    await expect(page.getByTestId("outcome-summary").getByTestId("ff-sample-size")).toContainText("1 treated customer ordered");
    await expect(measure).toHaveAttribute("data-done", "true");
    await expect(page.getByRole("button", { name: "Fast-forward one day" })).toBeDisabled();

    const outs = await (await page.request.get(`${API}/outcomes`, { headers: h })).json();
    const tea = outs.find((o: { play_id: string }) => o.play_id === "play_tea_ds04_v1");
    expect(tea.status).toBe("measured");
    expect(tea.treated.responders).toBe(1);
    expect(tea.data_label).toBe("SYNTHETIC");
    await shot(page, "ff-03-tea");
    await expectNoConsoleErrors(errors);
  });
});
