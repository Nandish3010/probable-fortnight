import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import { clearMockFaults, injectMockFaults, mockCalls } from "./helpers";

// Every failed load and call renders an ErrorCard (role="alert") instead of a spinner or silence.
// Mock mode, with the failure injected through web/lib/mockFaults.ts. The real network path (a
// blocked origin, a hung server, a 503 on the wire) is tested in blocked-origin.spec.ts and
// api-fetch.spec.ts.

test.describe("Play Desk", () => {
  test("a failing plays load shows the card within 10 s; Retry recovers", async ({ page }) => {
    await injectMockFaults(page, { "/plays": { kind: "network" } });
    await page.goto("/desk");
    const card = page.getByTestId("error-card");
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card).toContainText("Can't reach the Taal service");
    await expect(page.getByText("Loading plays…")).toHaveCount(0);
    await clearMockFaults(page);
    await card.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first()).toBeVisible();
    await expect(page.getByTestId("error-card")).toHaveCount(0);
  });

  test("Show recorded result lists the shipped plays and says so", async ({ page }) => {
    await injectMockFaults(page, { "/plays": { kind: "timeout" } });
    await page.goto("/desk");
    const card = page.getByTestId("error-card");
    await expect(card).toContainText("This is taking longer than expected");
    await card.getByRole("button", { name: "Show recorded result" }).click();
    await expect(page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first()).toBeVisible();
    await expect(page.getByTestId("recorded-note")).toContainText("REPLAY");
    await expect(page.getByTestId("error-card")).toHaveCount(0);
  });

  test("a failing trace read shows a compact card with Retry in the trace section", async ({ page }) => {
    await injectMockFaults(page, { "/events": { kind: "http" } });
    await page.goto("/desk");
    const card = page.getByTestId("play-detail").getByTestId("error-card");
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card).toContainText("Something went wrong");
    await clearMockFaults(page);
    await card.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("play-detail").locator(".trace-panel")).toBeVisible();
  });

  test("a failing policy read is reported where it happens", async ({ page }) => {
    await injectMockFaults(page, { "/policy": { kind: "network" } });
    await page.goto("/desk");
    const policy = page.locator(".policy-editor").getByTestId("error-card");
    await expect(policy).toBeVisible({ timeout: 10_000 });
    await clearMockFaults(page);
    await policy.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByLabel("Policy text")).toBeVisible();
  });

  test("Plan live that cannot start says why, with Retry", async ({ page }) => {
    await injectMockFaults(page, { "/rerun": { kind: "model_unavailable", retry_after_s: 1, times: 1 } });
    await page.goto("/desk");
    await page.getByTestId("plan-live").click();
    const card = page.getByTestId("play-detail").getByTestId("error-card");
    await expect(card).toContainText("The AI model is busy");
    await expect(card.getByRole("button", { name: "Retry" })).toBeEnabled({ timeout: 5_000 });
    await card.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("live-replan")).toBeVisible();
  });
});

test.describe("Approve", () => {
  async function openBeat(page: import("@playwright/test").Page) {
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
  }

  test("409: the recorded result is shown with its banner and no animation, no error card", async ({ page }) => {
    await injectMockFaults(page, { "/approve": { kind: "conflict" } });
    await openBeat(page);
    await page.getByRole("button", { name: "Approve" }).click();
    const result = page.getByTestId("approve-result");
    await expect(result).toBeVisible();
    await expect(result).toHaveAttribute("data-phase", "alreadyApproved");
    await expect(result).toHaveAttribute("data-motion", "off");
    await expect(page.getByTestId("already-approved-banner")).toHaveText("Already approved. Showing the recorded result.");
    await expect(result.getByRole("heading", { name: "Approved: Darjeeling Tea 100G" })).toBeFocused();
    await expect(page.getByTestId("approve-steps")).toHaveCount(0);
    await expect(page.getByTestId("approve-error")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
    // it is final: the figure is already the canonical one, with no count-up
    await expect(result.getByTestId("approve-recovered-amount")).toHaveText("₹7,498");
  });

  test("404: the sandbox was restarted", async ({ page }) => {
    await injectMockFaults(page, { "/approve": { kind: "not_found" } });
    await openBeat(page);
    await page.getByRole("button", { name: "Approve" }).click();
    const error = page.getByTestId("approve-error");
    await expect(error).toContainText("This demo session was restarted");
    await expect(error).toContainText("Your sandbox was reset. Run the demo again from the start.");
  });

  test("a failed approve says so once, and Retry completes it", async ({ page }) => {
    await injectMockFaults(page, { "/approve": { kind: "http", times: 1 } });
    await openBeat(page);
    await page.getByRole("button", { name: "Approve" }).click();
    const error = page.getByTestId("approve-error");
    await expect(error).toContainText("Something went wrong");
    await expect(page.getByTestId("approve-error")).toHaveCount(1);
    await expect(page.getByTestId("approve-result")).toHaveCount(0);
    await error.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("approve-result")).toBeVisible({ timeout: 15_000 });
    expect(await mockCalls(page, "/approve")).toBe(2);
  });

  test("the error card passes axe", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await injectMockFaults(page, { "/approve": { kind: "http" } });
    await openBeat(page);
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByTestId("approve-error")).toBeVisible();
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
  });
});

test.describe("Chat: 503 model_unavailable", () => {
  test("shows 'The AI model is busy' with the stated seconds; Retry unlocks after them and re-sends once", async ({ page }) => {
    await injectMockFaults(page, { "/chat": { kind: "model_unavailable", retry_after_s: 2, times: 1 } });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click(); // pre-filled "Any offers today?"
    const card = page.getByTestId("error-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("role", "alert");
    await expect(card).toContainText("The AI model is busy");
    await expect(card).toContainText("Try again in 2 seconds");

    // Retry is there from the start but waits out the 2 seconds the server asked for
    const retry = card.getByRole("button", { name: /Retry/ });
    await expect(retry).toBeDisabled();
    await expect(retry).toHaveText(/Retry in \d s/);
    await expect(retry).toBeEnabled({ timeout: 6_000 });
    await expect(retry).toHaveText("Retry");

    const log = page.getByTestId("chat-log");
    await retry.click();
    await expect(log.locator(".chat-msg--agent").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("error-card")).toHaveCount(0);
    // the visitor's message was not added a second time, and the old doubled error text is gone
    await expect(log.locator(".chat-msg--customer")).toHaveCount(1);
    await expect(log).not.toContainText(/live call failed/i);
  });

  test("429 says 'Too many requests' and how long to wait", async ({ page }) => {
    await injectMockFaults(page, { "/chat": { kind: "rate_limited", retry_after_s: 9, times: 1 } });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("error-card")).toContainText("Too many requests");
    await expect(page.getByTestId("error-card")).toContainText("Please wait 9 seconds and try again.");
  });
});

test.describe("Phone: capture", () => {
  test("503 model_unavailable on /capture shows the card; Retry reads the pallet after the wait", async ({ page }) => {
    await injectMockFaults(page, { "/capture": { kind: "model_unavailable", retry_after_s: 2, times: 1 } });
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toContainText("The AI model is busy");
    await expect(card).toContainText("Try again in 2 seconds");
    await expect(page.getByTestId("intake-table")).toHaveCount(0);
    const retry = card.getByRole("button", { name: /Retry/ });
    await expect(retry).toBeEnabled({ timeout: 6_000 });
    await retry.click();
    await expect(page.getByTestId("intake-table")).toBeVisible();
    await expect(page.getByTestId("error-card")).toHaveCount(0);
  });

  test("a failing confirm and a failing 'Done' are reported, not swallowed", async ({ page }) => {
    await injectMockFaults(page, {
      "/capture/confirm": { kind: "network", times: 1 },
      "/execution": { kind: "http", times: 1 },
    });
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toContainText("Can't reach the Taal service");
    await card.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("why-now")).toContainText("₹9,200");

    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByRole("heading", { name: "Execution steps" })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByTestId("error-card")).toContainText("Something went wrong");
    await page.getByTestId("error-card").getByRole("button", { name: "Retry" }).click();
    await expect(page.getByText("Execution recorded.")).toBeVisible();
  });
});

test.describe("Outcomes", () => {
  test("a failing outcomes read shows the card; Show recorded result fills the table and says so", async ({ page }) => {
    await injectMockFaults(page, { "/outcomes": { kind: "http" } });
    await page.goto("/outcomes");
    await expect(page.getByRole("button", { name: "Show recorded result" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Loading…", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Show recorded result" }).click();
    await expect(page.locator(".outcomes-table")).toContainText("Masala Chips 200G");
    await expect(page.getByTestId("recorded-note")).toContainText("REPLAY");
  });

  test("Run Measure that fails explains what to do and can be retried", async ({ page }) => {
    await injectMockFaults(page, { "/measure": { kind: "http", times: 1 } });
    await page.goto("/outcomes");
    await page.getByRole("button", { name: "Run Measure" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toContainText("Measure did not run");
    await expect(card).toContainText("Approve a play first, then try again.");
    await card.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByText(/plays? joined against orders/)).toBeVisible();
  });
});
