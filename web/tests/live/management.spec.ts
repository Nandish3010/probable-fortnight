import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

test.describe("Management: outcomes", () => {
  test("empty state, then measured and unmeasured rows", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-mgmt";
    await asVisitor(page, vid);
    await page.goto("/outcomes");
    await expect(page.getByRole("heading", { name: "Outcomes" })).toBeVisible();
    await expect(page.getByTestId("outcome-summary")).toContainText("Nothing is measured in your session yet. Approve a play, then Run Measure.");
    // Built once with the tenant: present before this visitor measures anything, and unchanged after.
    const priorLine = page.locator(".prior-update").getByText(/Estimator prior: Beta\(1,19\) → Beta\(17,326\) · SYNTHETIC orders/);
    await expect(priorLine).toBeVisible();
    await shot(page, "mgmt-01-empty");

    const h = visitorHeaders(vid);
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_chips_ds07_v1" } });
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_kaju_ds03_v1" } });
    await page.request.post(`${API}/chat`, { headers: { ...h, Accept: "application/json" }, data: { session_id: "CUST-MEENA:web", text: "Any offers?" } });
    await page.request.post(`${API}/chat`, { headers: { ...h, Accept: "application/json" }, data: { session_id: "CUST-MEENA:web", text: "add:SKU-MASALA-CHIPS-200G" } });

    // Measure is a button now, not something that runs on its own: nothing populates this page
    // until a visitor clicks it.
    await page.getByRole("button", { name: "Run Measure" }).click();
    await expect(page.getByText(/measured, .* unmeasured/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Masala Chips 200G").first()).toBeVisible();
    await expect(page.getByText("SYNTHETIC").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Looker/ })).toHaveCount(0);
    await expect(page.getByTestId("outcome-summary")).toContainText("Response-rate difference");
    await expect(priorLine).toBeVisible();
    const outs = await (await page.request.get(`${API}/outcomes`, { headers: h })).json();
    const chips = outs.find((o: { play_id: string }) => o.play_id === "play_chips_ds07_v1");
    expect(chips.status).toBe("measured");
    expect(chips.treated.responders).toBeGreaterThanOrEqual(1);
    expect(chips.holdout.customers).toBeGreaterThanOrEqual(1);
    for (const o of outs) if (o.status === "unmeasured") expect(o.lift).toBeUndefined();
    await shot(page, "mgmt-02-measured");
    await expectNoConsoleErrors(errors);
  });
});
