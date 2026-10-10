import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { FF_EXPLAINER, orderRequest, pickTreatedPersona, sampleSizeLine, stepLabel } from "../../lib/fastForward";
import { deriveProgress, EMPTY_CRUMBS, NO_FACTS, type ApiFacts } from "../../lib/progress";
import { newcombeInterval } from "../../lib/mockMeasure";
import type { DemoCustomer, Outcome } from "../../lib/types";
import {
  FAKE_API,
  assertNoHorizontalOverflow,
  beatHandlers,
  clearMockFaults,
  fakeApi,
  forceLiveApi,
  injectMockFaults,
  mockCalls,
  mockFixture,
  okJson,
} from "./helpers";

// E2, "Fast-forward one day" on Outcomes, driven end to end in mock mode. The mock chat order and
// Measure (lib/api.ts, lib/mockMeasure.ts) stand in for the sandbox, so the panel runs the same
// existing calls it runs against the real API. Tea (the hero play) has no measured row in the
// fixtures, which is the "approved, nothing measured" state the panel is for.
const TEA = "play_tea_ds04_v1";

async function approvedTea(page: Page): Promise<void> {
  await page.addInitScript((id) => {
    try {
      if (!window.sessionStorage.getItem("taal_seeded")) {
        window.localStorage.setItem("taal_mock_approved", JSON.stringify([id]));
        window.sessionStorage.setItem("taal_seeded", "1");
      }
    } catch {
      // storage blocked: the test fails on its own assertion
    }
  }, TEA);
}

const panel = (page: Page) => page.getByTestId("fast-forward");
const go = (page: Page) => page.getByTestId("fast-forward-go");

async function openOutcomes(page: Page): Promise<void> {
  await approvedTea(page);
  await page.goto("/outcomes");
  await expect(panel(page)).toBeVisible();
}

async function storage(page: Page, key: string): Promise<unknown> {
  return page.evaluate((k) => {
    const raw = localStorage.getItem(k);
    return raw ? JSON.parse(raw) : null;
  }, key);
}

test.describe("fast-forward: pure logic", () => {
  const people: DemoCustomer[] = [
    { customer_id: "CUST-MEENA", display_name: "Meena", home_node_id: "DS-07", language: "kn", role: "sample", note: "" },
    { customer_id: "CUST-RAVI", display_name: "Ravi", home_node_id: "DS-04", language: "en", role: "sample", note: "" },
    { customer_id: "CUST-00316", display_name: "Divya", home_node_id: "DS-07", language: "kn", role: "holdout", note: "" },
  ];

  test("the treated persona is a sample customer, preferring one at the play's store; never the holdout", () => {
    expect(pickTreatedPersona(people, ["DS-04"])?.display_name).toBe("Ravi");
    expect(pickTreatedPersona(people, ["DS-07"])?.display_name).toBe("Meena");
    expect(pickTreatedPersona(people, ["DS-99"])?.display_name).toBe("Meena");
    expect(pickTreatedPersona([people[2]], ["DS-07"])).toBeNull();
    expect(pickTreatedPersona([], ["DS-07"])).toBeNull();
  });

  test("the order is the existing chat quick reply", () => {
    expect(orderRequest("CUST-MEENA", "SKU-MASALA-CHIPS-200G")).toEqual({ session_id: "CUST-MEENA:web", text: "add:SKU-MASALA-CHIPS-200G" });
    expect(stepLabel("order", "Meena")).toBe("Placing Meena's order");
    expect(stepLabel("measure", "Meena")).toBe("Measuring against the holdout");
  });

  test("one order against a holdout of none: the interval crosses zero", () => {
    const ci = newcombeInterval(1, 291, 0, 32);
    expect(ci.low).toBeLessThan(0);
    expect(ci.high).toBeGreaterThan(0);
  });

  test("sampleSizeLine reads the measured row", () => {
    const arm = (customers: number, responders: number) => ({ customers, responders, units: responders, revenue_inr: 0, margin_inr: 0, discount_cost_inr: 0 });
    const row = { treated: arm(291, 1), holdout: arm(32, 0) } as unknown as Outcome;
    expect(sampleSizeLine(row)).toBe("1 treated customer ordered (of 291); 0 of 32 holdout customers ordered.");
  });

  test("Measure is done only by a measured row for a play the visitor approved", () => {
    const facts = (over: Partial<ApiFacts>): ApiFacts => ({ ...NO_FACTS, ...over });
    const plays = [{ play_id: "p1", gap_id: "g", status: "approved" }];
    const seeded = [{ status: "measured", play_id: "someone_elses" }];
    expect(deriveProgress("g", EMPTY_CRUMBS, facts({ plays, outcomes: seeded })).measure).toBe(false);
    expect(deriveProgress("g", EMPTY_CRUMBS, facts({ plays, outcomes: [{ status: "measured", play_id: "p1" }] })).measure).toBe(true);
    expect(deriveProgress("g", EMPTY_CRUMBS, facts({ plays, outcomes: [{ status: "unmeasured", play_id: "p1" }] })).measure).toBe(false);
  });
});

test.describe("fast-forward: the panel", () => {
  test("is offered once a play is approved and nothing is measured, labelled SYNTHETIC, and not before", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByTestId("outcome-summary")).toBeVisible();
    await page.waitForTimeout(600);
    await expect(panel(page)).toHaveCount(0); // nothing approved

    await page.context().clearCookies();
    await openOutcomes(page);
    await expect(panel(page).getByRole("heading", { name: "See what measuring looks like" })).toBeVisible();
    await expect(panel(page).locator(".badge--synthetic")).toContainText("SYNTHETIC");
    await expect(panel(page)).toContainText("sandbox demonstration, not a result");
    await expect(go(page)).toBeEnabled();
    await expect(go(page)).toHaveText("Fast-forward one day");
    await expect(page.getByTestId("outcome-summary")).toContainText("Nothing is measured in your session yet");
  });

  test("success: honest steps with real times, then the measured row, Inconclusive, points, sample size and the explainer", async ({ page }) => {
    await openOutcomes(page);
    await go(page).click();
    // the steps use the treated persona's own name and the real elapsed time
    const steps = page.getByTestId("fast-forward-steps");
    await expect(steps).toBeVisible();
    await expect(steps).toContainText("Placing Ravi's order");
    await expect(steps).toContainText("Measuring against the holdout");
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
    await expect(steps.locator('li[data-status="done"]')).toHaveCount(3);
    await expect(steps.locator("li").nth(1)).toContainText(/\(\d+(\.\d)? s\)/);

    const summary = page.getByTestId("outcome-summary");
    await expect(summary.getByRole("heading", { name: /Your result: / })).toBeVisible();
    await expect(summary.getByTestId("inconclusive-badge")).toBeVisible();
    await expect(summary.locator(".badge--synthetic").first()).toHaveText("SYNTHETIC");
    await expect(summary.getByTestId("summary-difference")).toContainText("+0.3 points");
    await expect(summary.getByTestId("summary-difference")).toContainText("95% CI");
    await expect(summary.getByTestId("ff-sample-size")).toContainText("1 treated customer ordered");
    await expect(summary.getByTestId("ff-explainer")).toHaveText(FF_EXPLAINER);
    await expect(summary.getByTestId("ff-explainer")).toHaveText(
      "One order is far too few to prove an effect. This shows the loop working; a pilot would supply the real numbers.",
    );
    // withheld, not zero
    await expect(summary.getByTestId("summary-ceo")).toContainText("withheld: inconclusive");
    // the stepper now says Measure is done
    await expect(page.getByTestId("stepper").locator('li[data-step="measure"]')).toHaveAttribute("data-done", "true");
    // the same row is in the table, labelled SYNTHETIC
    const row = page.locator(".outcomes-table tbody tr").filter({ hasText: "Darjeeling" });
    await expect(row.getByTestId("inconclusive-badge")).toBeVisible();
    // no word "real" is used for the data
    await expect(panel(page)).not.toContainText(/real customer/i);
  });

  test("idempotent: after success the button is disabled and says so; a reload keeps it that way", async ({ page }) => {
    await openOutcomes(page);
    await go(page).click();
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
    await expect(go(page)).toBeDisabled();
    await expect(page.getByTestId("fast-forward-already")).toHaveText("Already fast-forwarded in this session");
    expect(await mockCalls(page, "/chat")).toBe(1);

    await page.reload();
    await expect(panel(page)).toBeVisible();
    await expect(go(page)).toBeDisabled();
    await expect(page.getByTestId("fast-forward-already")).toBeVisible();
    await expect(page.getByTestId("outcome-summary").getByTestId("ff-explainer")).toBeVisible();
    expect(await storage(page, "taal_mock_orders")).toHaveLength(1);
  });

  test("Reset demo data clears the crumb and the synthetic rows: the button works again", async ({ page }) => {
    await openOutcomes(page);
    await go(page).click();
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
    await page.goto("/");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByRole("dialog", { name: "Reset demo data?" }).getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByRole("button", { name: "Reset demo data" })).toBeEnabled();
    await page.evaluate((id) => localStorage.setItem("taal_mock_approved", JSON.stringify([id])), TEA);
    await page.goto("/outcomes");
    await expect(panel(page)).toBeVisible();
    await expect(go(page)).toBeEnabled();
    expect(await storage(page, "taal_mock_measured")).toBeNull();
  });

  test("the chat order fails: an ErrorCard with Retry, nothing placed, nothing measured, then Retry works", async ({ page }) => {
    await approvedTea(page);
    await injectMockFaults(page, { "/chat": { kind: "network" } });
    await page.goto("/outcomes");
    await go(page).click();
    const card = panel(page).getByTestId("error-card");
    await expect(card).toBeVisible();
    await expect(card).toContainText("order did not go through");
    await expect(card).toContainText("Nothing was ordered and nothing was measured");
    await expect(card.getByTestId("error-retry")).toBeVisible();
    await expect(panel(page).locator('li[data-status="failed"]')).toHaveCount(1);
    expect(await storage(page, "taal_mock_orders")).toBeNull();
    expect(await mockCalls(page, "/measure")).toBe(0);
    await expect(page.getByTestId("outcome-summary")).toContainText("Nothing is measured in your session yet");
    await expect(page.getByTestId("ff-sample-size")).toHaveCount(0);

    await clearMockFaults(page);
    await card.getByTestId("error-retry").click();
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
    expect(await storage(page, "taal_mock_orders")).toHaveLength(1);
  });

  test("Measure fails after the order: says so, offers Run Measure only, and does not order twice", async ({ page }) => {
    await approvedTea(page);
    await injectMockFaults(page, { "/measure": { kind: "network", times: 1 } });
    await page.goto("/outcomes");
    await go(page).click();
    const card = panel(page).getByTestId("error-card");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Order placed. Measure failed.");
    await expect(card).toContainText("Ravi's synthetic order was placed");
    await expect(card.getByTestId("error-retry")).toHaveCount(0);
    await expect(go(page)).toHaveCount(0); // no way to place the order again
    await expect(panel(page).getByTestId("fast-forward-run-measure")).toBeVisible();
    expect(await storage(page, "taal_mock_orders")).toHaveLength(1);
    await expect(page.getByTestId("outcome-summary")).toContainText("Nothing is measured in your session yet");

    await panel(page).getByTestId("fast-forward-run-measure").click();
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
    expect(await mockCalls(page, "/chat")).toBe(1);
    expect(await storage(page, "taal_mock_orders")).toHaveLength(1);
    await expect(page.getByTestId("outcome-summary").getByTestId("ff-sample-size")).toContainText("1 treated customer ordered");
    await expect(go(page)).toBeDisabled();
  });

  test("no treated persona in the sandbox: an ErrorCard with Retry and nothing ordered", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const plays = mockFixture("plays").map((p: { play_id: string }) => (p.play_id === TEA ? { ...p, status: "approved" } : p));
    let chatCalls = 0;
    await fakeApi(
      page,
      beatHandlers({
        "/plays": okJson(plays),
        "/outcomes": okJson([]),
        "/outcomes/prior-update": okJson(mockFixture("prior_update")),
        "/customers/demo": okJson(mockFixture("customers_demo").filter((c: { role: string }) => c.role === "holdout")),
        "/chat": (route) => {
          chatCalls += 1;
          return route.fulfill({ status: 500, body: "{}" });
        },
      }),
    );
    await page.goto("/outcomes");
    await expect(panel(page)).toBeVisible();
    await go(page).click();
    const card = panel(page).getByTestId("error-card");
    await expect(card).toContainText("No treated customer to order for");
    await expect(card.getByTestId("error-retry")).toBeVisible();
    expect(chatCalls).toBe(0);
  });
});

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 375, height: 812 }]] as const) {
    test.describe(`fast-forward: axe (${scheme}, ${name})`, () => {
      test.use({ viewport, colorScheme: scheme });
      const tags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

      test("idle, failed (chat) and finished states have no violations", async ({ page }) => {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await approvedTea(page);
        await injectMockFaults(page, { "/chat": { kind: "network" } });
        await page.goto("/outcomes");
        await expect(panel(page)).toBeVisible();
        await page.waitForTimeout(300);
        let results = await new AxeBuilder({ page }).withTags(tags).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);

        await go(page).click();
        await expect(panel(page).getByTestId("error-card")).toBeVisible();
        results = await new AxeBuilder({ page }).withTags(tags).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);

        await clearMockFaults(page);
        await panel(page).getByTestId("error-retry").click();
        await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
        await page.waitForTimeout(300);
        results = await new AxeBuilder({ page }).withTags(tags).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });

      test("measure-failed state has no violations", async ({ page }) => {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await approvedTea(page);
        await injectMockFaults(page, { "/measure": { kind: "network" } });
        await page.goto("/outcomes");
        await go(page).click();
        await expect(panel(page).getByTestId("fast-forward-run-measure")).toBeVisible();
        const results = await new AxeBuilder({ page }).withTags(tags).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });
    });
  }
}

test.describe("fast-forward: 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("idle, running, failed, measure-failed and finished states do not overflow sideways", async ({ page }) => {
    await approvedTea(page);
    await injectMockFaults(page, { "/chat": { kind: "network", times: 1 } });
    await page.goto("/outcomes");
    await expect(panel(page)).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await go(page).click();
    await expect(panel(page).getByTestId("error-card")).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await panel(page).getByTestId("error-retry").click();
    await expect(page.getByTestId("fast-forward-steps")).toBeVisible();
    await assertNoHorizontalOverflow(page);
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 15_000 });
    await assertNoHorizontalOverflow(page);
  });

  test("the measure-failed state does not overflow sideways", async ({ page }) => {
    await approvedTea(page);
    await injectMockFaults(page, { "/measure": { kind: "network" } });
    await page.goto("/outcomes");
    await go(page).click();
    await expect(panel(page).getByTestId("fast-forward-run-measure")).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });
});
