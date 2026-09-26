import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";

// States the route scan in a11y.spec.ts never reaches (errors shown, results loaded).
async function expectAxeClean(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

// Mock mode: the form comes from web/mocks/feedback_form.json (an exact copy of
// config/feedback_form.json, checked in tests/contract) and submitting stores nothing anywhere.
// Runs at desktop and at a real phone viewport (playwright.config.ts `mobile` project).

async function pick(page: Page, group: string, option: string) {
  await page.getByRole("group", { name: group }).getByLabel(option, { exact: true }).check();
}

test("completes the form, skipping from c0 = No straight to section D", async ({ page }) => {
  await page.goto("/feedback?mode=interview&source=test");
  await expect(page.getByText("Interview mode")).toBeVisible();
  await expect(page.getByText("Test mode")).toBeVisible();

  await pick(page, "Which best describes your role? (required)", "Store or dark-store manager");
  await pick(page, "What kind of business do you work in? (required)", "Quick-commerce or dark stores");
  await pick(page, "How often does stock go unsold before its date?", "Weekly");
  await page.getByRole("group", { name: "What do you usually do with near-expiry stock?" }).getByLabel("Blanket markdown").check();
  await expect(page.getByText("FSSAI asks that food sold online has at least 30% of its shelf life")).toBeVisible();
  await pick(page, "Were you aware of this?", "Not sure");

  const usefulness = page.getByRole("group", { name: /How useful would lot-level offers/ });
  await pick(page, "Have you seen Taal working?", "Yes, live");
  await expect(usefulness).toBeVisible();
  await pick(page, "Have you seen Taal working?", "No");
  await expect(usefulness).toHaveCount(0);
  await expect(page.getByRole("group", { name: /How would you prefer to pay/ })).toHaveCount(0);

  await page.getByLabel("What is the single biggest problem with near-expiry stock in your business?").fill("Test entry from the e2e suite.");
  await expect(page.getByLabel("Name")).toHaveCount(0);
  await pick(page, "Would you consider a one-week pilot?", "Maybe");
  await expect(page.getByLabel("Email or phone")).toBeVisible();
  await pick(page, "May we quote your answers anonymously, showing only your role and business type?", "No");
  await page.getByLabel(/I have read the statement above/).check();

  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", /\d+/);
  await page.getByRole("button", { name: "Submit" }).click();
  await expect(page.getByRole("heading", { name: "Thank you. Your response has been recorded." })).toBeFocused();
  await expect(page.getByTestId("feedback-reference")).toHaveText(/^[0-9a-f]{32}$/);
});

test("pay amount appears only for monthly per store, and c2 stops at two", async ({ page }) => {
  await page.goto("/feedback?source=test");
  await pick(page, "Have you seen Taal working?", "Yes, video or screenshots");
  const amount = page.getByRole("group", { name: "Roughly how much per store per month?" });
  await pick(page, "How would you prefer to pay for something like this?", "One-time fee");
  await expect(amount).toHaveCount(0);
  await pick(page, "How would you prefer to pay for something like this?", "Monthly per store");
  await expect(amount).toBeVisible();

  const c2 = page.getByRole("group", { name: "Which parts would be most valuable?" });
  await c2.getByLabel("Online sell-by deadline per lot").check();
  await c2.getByLabel("A person approves before anything goes out").check();
  await expect(c2.getByLabel("Offers sent to customers in their own language")).toBeDisabled();
});

test("missing required answers are announced and linked", async ({ page }) => {
  await page.goto("/feedback?source=test");
  await page.getByRole("button", { name: "Submit" }).click();
  const alert = page.getByRole("alert").filter({ hasText: "Please fix these before submitting" });
  await expect(alert).toBeVisible();
  await expect(alert).toBeFocused();
  await expect(alert.getByRole("link")).toHaveCount(3);
  await expect(page.getByText("Please tick the consent box to submit.", { exact: true })).toBeVisible();
  await expectAxeClean(page);
  await expect(page.getByLabel(/I have read the statement above/)).toHaveAttribute("aria-invalid", "true");
});

test("landing footer links to the form; the top navigation does not", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("footer").getByRole("link", { name: "Practitioner feedback" })).toHaveAttribute("href", "/feedback");
  await expect(page.locator("nav.top-nav").getByRole("link", { name: /feedback/i })).toHaveCount(0);
});

test("results page in mock mode shows no simulated numbers", async ({ page }) => {
  await page.goto("/feedback/results");
  await page.getByLabel("Admin token").fill("anything");
  await page.getByRole("button", { name: "Show results" }).click();
  await expect(page.getByText("No real responses yet.")).toBeVisible();
  await expectAxeClean(page);
});
