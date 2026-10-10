import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

test.describe("judge: landing", () => {
  test("60-second beat, idempotent approve, chat, reset, isolation", async ({ page, browser }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-judge-a");
    await page.goto("/");
    await expect(page.getByTestId("demo-clock")).toContainText("Nothing you do here persists.");
    await expect(page.getByText(/300 SKUs|SKUs/)).toBeVisible();
    await shot(page, "judge-01-landing");

    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const beat = page.getByTestId("beat-panel");
    // The beat opens on HERO_GAP_ID (app/page.tsx): the Darjeeling Tea lot at Dark store 4.
    await expect(beat.getByTestId("why-now")).toContainText("₹35,020");
    await expect(beat.locator(".gap-card__stats .stat__value").nth(2)).toHaveText("24d"); // the demo clock is pinned
    await beat.getByTestId("card-details").locator("summary").click(); // the sell-by rule is in Details
    await expect(beat.getByText(/v1-either/)).toBeVisible();
    await shot(page, "judge-02-gap-card");

    await beat.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    const writeoffText = await page.getByTestId("writeoff-line").innerText();
    expect(writeoffText).toContain("→");
    const [writeoffBefore, writeoffAfter] = [...writeoffText.matchAll(/[\d,]+(?:\.\d+)?/g)].map((m) => Number(m[0].replace(/,/g, "")));
    expect(writeoffAfter).toBeLessThan(writeoffBefore); // the write-off must genuinely count down, not just show two numbers
    await expect(page.getByText(/holdout/i).first()).toBeVisible();
    // the forecast run id moved into the result's Details (the heading no longer leaks ids)
    await page.getByTestId("approve-details").locator("summary").click();
    await expect(page.getByText(/refc_play_tea_ds04_v1/)).toBeVisible();
    await shot(page, "judge-03-approved-chart");

    // second approve must be idempotent
    const again = await page.request.post(`${API}/approve`, { headers: visitorHeaders("live-judge-a"), data: { play_id: "play_tea_ds04_v1" } });
    expect((await again.json()).note).toContain("already approved");

    // Meena's offer is for the chips bundle, so approve that play (API, not the beat) before chatting.
    await page.request.post(`${API}/approve`, { headers: visitorHeaders("live-judge-a"), data: { play_id: "play_chips_ds07_v1" } });

    // chat as Meena after approval: the offer arrives, mentioning the bundle price. The live
    // Gemini-backed Customer Agent paraphrases freely and does not reliably reply in Kannada even
    // for this Kannada-preference customer (observed live, both in and out of CI), so this checks
    // the one stable fact -- the real price cited -- rather than an exact phrase or language.
    const chat = page.getByTestId("chat-log");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(chat.getByText(/58\.5/)).toBeVisible({ timeout: 15_000 });
    await expect(chat.getByRole("button", { name: /ಕಾರ್ಟ್|Add to cart/ })).toBeVisible();
    await shot(page, "judge-04-chat-offer");

    // isolation: another visitor still sees the play as proposed
    const other = await browser.newContext();
    const p2 = await other.newPage();
    await asVisitor(p2, "live-judge-b");
    const r = await p2.request.get(`${API}/plays/play_tea_ds04_v1`, { headers: visitorHeaders("live-judge-b") });
    expect((await r.json()).status).toBe("proposed");
    await other.close();

    // reset scoped to this visitor
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Reset", exact: true }).click(); // Reset asks first
    await expect(page.getByRole("button", { name: "Reset demo data" })).toBeEnabled();
    const after = await page.request.get(`${API}/plays/play_tea_ds04_v1`, { headers: visitorHeaders("live-judge-a") });
    expect((await after.json()).status).toBe("proposed");
    await shot(page, "judge-05-after-reset");
    await expectNoConsoleErrors(errors);
  });

  test("first paint under 4s from a cold hit", async ({ page }) => {
    await asVisitor(page, "live-judge-perf");
    await page.goto("/");
    const fcp = await page.evaluate(
      () => new Promise<number>((resolve) => {
        const existing = performance.getEntriesByType("paint").find((e) => e.name === "first-contentful-paint");
        if (existing) return resolve(existing.startTime);
        new PerformanceObserver((list) => {
          const entry = list.getEntriesByName("first-contentful-paint")[0];
          if (entry) resolve(entry.startTime);
        }).observe({ type: "paint", buffered: true });
      })
    );
    expect(fcp).toBeLessThan(4000);
  });

  test("health strip turns amber when a dependency check fails", async ({ page }) => {
    await asVisitor(page, "live-judge-health");
    await page.route("**/health", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      body.checks.vertex.ok = false;
      body.status = "degraded";
      await route.fulfill({ response: res, json: body });
    });
    await page.goto("/");
    await expect(page.locator(".health-strip__item--amber")).toBeVisible();
    // every other check in the crafted payload stayed healthy, so the strip is not all-amber
    await expect(page.locator(".health-strip__item--ok").first()).toBeVisible();
    // The landing page fires two independent GET /health calls on mount (HealthStrip and
    // TenantLine each call getHealth() in their own effect, HealthStrip.tsx) -- both hit this
    // one page.route handler. The assertions above only need the first response to land; the
    // second invocation can still be awaiting route.fetch() when the test (and then the page)
    // closes, which throws "Target page, context or browser has been closed" and fails the test
    // on a passing run. unrouteAll's ignoreErrors silently drops that in-flight handler instead
    // of letting its rejection surface, per Playwright's own suggestion in that error message.
    await page.unrouteAll({ behavior: "ignoreErrors" });
  });
});
