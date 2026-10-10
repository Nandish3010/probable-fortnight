import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { approveSettled, assertNoHorizontalOverflow, injectMockFaults, openBeat, setMockDelay } from "./helpers";

// The demo-path details found in review (mock mode, desktop): the offer goes to a customer who is in
// the approved play's audience; the model chip and the trace header; the estimate range in units.
// The phone's no-risk card is in capture-phone.spec.ts and phone.spec.ts.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const approveButton = (page: Page) => page.getByTestId("approve-button").first();

async function approveOnDesk(page: Page, product: RegExp) {
  await page.goto("/desk");
  await page.getByLabel("Play inbox").getByRole("button", { name: product }).first().click();
  const card = page.getByTestId("play-detail");
  await card.getByTestId("approve-button").click();
  await card.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
  return card;
}

test.describe("after Approve, the offer goes to a customer in the play's audience", () => {
  test("Tea (Dark store 4): the preview, the follow-up button and the chat panel use Ravi, not Meena", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    const preview = page.getByTestId("meena-preview");
    await expect(preview).toContainText("What Ravi receives");
    await expect(preview).not.toContainText("Meena");
    await expect(page.getByTestId("meena-audience-note")).toHaveCount(0);
    await expect(page.getByTestId("chat-as-customer")).toHaveText("Chat as Ravi");
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-RAVI");
    await expect(page.locator("#chat-panel h3")).toHaveText("Chat as Ravi");
    await expect(page.getByTestId("chat-customer-note")).toContainText("In the treated group once you approve");

    await page.getByTestId("chat-as-customer").click();
    await expect(page.getByLabel("Message")).toBeFocused();
    await expect(page.getByLabel("Message")).toHaveValue("Any offers today?");
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-RAVI");
  });

  test("the holdout follow-up still picks the holdout customer after the Tea approve", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await page.getByTestId("see-holdout").click();
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-00316");
  });

  test("a visitor's own pick is not overridden", async ({ page }) => {
    await openBeat(page);
    await page.getByTestId("chat-customer-select").selectOption("CUST-MEENA");
    await approveButton(page).click();
    await approveSettled(page);
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-MEENA");
  });

  test("the chips play (Dark store 7) still reaches Meena", async ({ page }) => {
    const card = await approveOnDesk(page, /Masala Chips 200G/);
    await expect(card.getByTestId("meena-preview")).toContainText("What Meena receives");
    await expect(card.getByTestId("chat-as-customer")).toHaveText("Chat as Meena");
    await card.getByTestId("chat-as-customer").click();
    await expect(page).toHaveURL(/\/chat\?as=prefill&customer=CUST-MEENA/);
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-MEENA");
    await expect(page.getByLabel("Message")).toHaveValue("Any offers today?");
  });

  test("on the Desk, Tea's 'Chat as Ravi' opens /chat as Ravi", async ({ page }) => {
    const card = await approveOnDesk(page, /Darjeeling Tea 100G/);
    await expect(card.getByTestId("chat-as-customer")).toHaveText("Chat as Ravi");
    await card.getByTestId("chat-as-customer").click();
    await expect(page).toHaveURL(/\/chat\?as=prefill&customer=CUST-RAVI/);
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-RAVI");
    await expect(page.locator("#chat-panel h3")).toHaveText("Chat as Ravi");
  });

  test("/chat opens on the customer of the play the visitor approved last; before any approval it is Meena", async ({ page }) => {
    await page.goto("/chat");
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-MEENA");
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await page.goto("/chat");
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-RAVI");
  });

  test("no copy promises an offer to Meena before the play is chosen", async ({ page }) => {
    await openBeat(page);
    await expect(page.getByTestId("chat-customer-note")).toHaveText("Receives the offer once the play is approved.");
    await page.goto("/chat");
    await expect(page.getByTestId("persona-bar")).not.toContainText(/offer/i);
  });
});

test.describe("first load on a slow API", () => {
  test("the chat's customer picker says 'Loading customers…' until the list arrives, never blank", async ({ page }) => {
    await setMockDelay(page, { "/customers/demo": 2500 });
    await page.goto("/");
    await expect(page.getByTestId("chat-customers-loading")).toHaveText("Loading customers…");
    await expect(page.getByTestId("chat-customer-select")).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId("chat-customers-loading")).toHaveCount(0);
  });
});

test.describe("estimate range is in units", () => {
  test("Details says 'Estimate range: 1 to 67 units', never a rupee range", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("card-details").locator("summary").click();
    const text = await card.getByTestId("card-details").innerText();
    expect(text).toMatch(/Estimate range: [\d,]+ to [\d,]+ units · prior n/);
    expect(text).not.toMatch(/Range ₹/);
  });
});

test.describe("model chip and trace header", () => {
  test("the trace header carries gemini-3.5-flash with the run time and no raw run id; the id is in technical details", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const trace = page.getByTestId("play-detail").locator(".trace-panel").first();
    const chip = trace.getByTestId("model-chip");
    await expect(chip).toHaveText(/^gemini-3\.5-flash( · \d+\.\d s)?$/);
    await expect(chip).toHaveAttribute("title", /Fallback: gemini-3\.5-flash-lite/);
    await expect(chip).not.toContainText("lite");
    // the four provenance badges are untouched
    await expect(trace.getByText("Recorded from Gemini")).toBeVisible();
    // no raw run id in the header or anywhere visible
    await expect(trace.locator(".trace-panel__header")).not.toContainText(/run_/);
    await expect(trace.getByTestId("trace-run-id")).toBeHidden();
    await trace.getByTestId("trace-technical-details").locator("summary").click();
    await expect(trace.getByTestId("trace-run-id")).toContainText(/Run run_/);
    // screen readers still get the run in the list's name
    await expect(trace.locator("ol.trace-panel__list")).toHaveAttribute("aria-label", /^Agent trace for run run_/);
  });

  test("when /health names no model the chip is absent and the header is otherwise unchanged", async ({ page }) => {
    await injectMockFaults(page, { "/health": { kind: "http" } });
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const trace = page.getByTestId("play-detail").locator(".trace-panel").first();
    await expect(trace.getByText("Recorded from Gemini")).toBeVisible();
    await expect(trace.getByRole("button", { name: /Replay at 4x/ })).toBeVisible();
    await expect(page.getByTestId("model-chip")).toHaveCount(0);
  });

  test("Plan live shows the chip in the live panel and the run time on the result", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("plan-live").click();
    const live = card.getByTestId("live-replan");
    await expect(live.getByTestId("model-chip")).toHaveText("gemini-3.5-flash"); // exact: no run time while the run is in flight
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    await expect(card.locator(".re-plan-result__meta").getByTestId("model-chip")).toHaveText("gemini-3.5-flash · 1.2 s");
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`demo path: axe and overflow, ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    test("Tea post-approve preview, and the Desk trace with the model chip", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await openBeat(page);
      await approveButton(page).click();
      await approveSettled(page);
      await page.getByTestId("meena-text").waitFor();
      await page.waitForTimeout(300);
      let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "approved: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
      await page.goto("/desk");
      await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
      await page.getByTestId("model-chip").first().waitFor();
      await page.getByTestId("trace-technical-details").first().locator("summary").click();
      await page.getByTestId("play-detail").getByTestId("card-details").locator("summary").click();
      await page.waitForTimeout(300);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "desk: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  });
}

test.describe("demo path: no horizontal overflow at 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });
  test("the Desk trace with the model chip and open details", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await page.getByTestId("model-chip").first().waitFor();
    await page.getByTestId("trace-technical-details").first().locator("summary").click();
    await assertNoHorizontalOverflow(page);
  });
});
