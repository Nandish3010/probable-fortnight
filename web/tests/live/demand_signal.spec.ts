import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, visitorHeaders } from "./helpers";

// Chat is a demand signal: two distinct customers asking for an out-of-stock product at the same
// node should show up as real evidence on that product's gap in the Play Desk, once Sense has had
// a chance to pick it up (here, via the on-demand redetect that a phone-view capture triggers).
test.describe("Demand signal: chat -> gap evidence -> Play Desk", () => {
  test("two customers asking for Cola Zero at DS-07 enrich the gap with real request counts", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-demand";
    await asVisitor(page, vid);
    const headers = visitorHeaders(vid);

    const customers = await (await page.request.get(`${API}/customers/demo?play_id=play_cola_ds07_v1`, { headers })).json();
    const meena = customers.find((c: { customer_id: string }) => c.customer_id === "CUST-MEENA");
    const other = customers.find((c: { role: string }) => c.role === "holdout");
    expect(meena?.home_node_id).toBe("DS-07");
    expect(other?.home_node_id).toBe("DS-07");
    expect(other.customer_id).not.toBe(meena.customer_id);

    for (const cid of [meena.customer_id, other.customer_id]) {
      const res = await page.request.post(`${API}/chat`, {
        headers,
        data: { session_id: `${cid}:web`, text: "Do you have Cola Zero?" },
      });
      expect(res.ok()).toBeTruthy();
    }

    // Trigger the on-demand Sense redetect for DS-07 (same mechanism the phone view uses after a
    // photo confirm) so the two requests just recorded are picked up before we look at /gaps.
    const captureRes = await page.request.post(`${API}/capture`, { headers, data: { node_id: "DS-07", photo_ref: "fixtures/photos/pallet_01.jpg" } });
    const captured = await captureRes.json();
    const rows = captured.rows.map((r: Record<string, unknown>) => ({ ...r, confirmed: true }));
    const confirmRes = await page.request.post(`${API}/capture/confirm`, { headers, data: { node_id: "DS-07", photo_ref: "fixtures/photos/pallet_01.jpg", rows } });
    const confirmed = await confirmRes.json();
    expect(confirmed.ok).toBeTruthy();
    expect(confirmed.gaps_refreshed).toBeGreaterThan(0);

    const gaps = await (await page.request.get(`${API}/gaps?node_id=DS-07&limit=500`, { headers })).json();
    const colaGap = gaps.find((g: { sku: string }) => g.sku === "SKU-COLA-ZERO-500ML");
    expect(colaGap).toBeTruthy();
    expect(colaGap.evidence.requests_count).toBeGreaterThanOrEqual(2);
    expect(colaGap.evidence.distinct_customers).toBe(2);

    await page.goto("/desk");
    const item = page.locator(".inbox__item", { hasText: "DS-07" }).filter({ hasText: "Cola" });
    await expect(item.first()).toBeVisible({ timeout: 15_000 });
    await item.first().click();
    await expect(page.getByTestId("play-detail").getByText(/Gap type:/)).toBeVisible();
    await expect(page.getByTestId("play-detail").getByText(/real chat requests? from 2 customers asking for this/)).toBeVisible();
    await expectNoConsoleErrors(errors);
  });
});
