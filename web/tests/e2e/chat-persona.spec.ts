import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { approveSettled, assertNoHorizontalOverflow, openBeat } from "./helpers";

// The persona line and the stepper's Offer sublabel on /chat follow the customer chosen in the chat
// panel's picker (lib/chatCustomer.ts). Other routes keep their persona.

const who = (page: Page) => page.getByTestId("persona-who");
const offerCaption = (page: Page) => page.locator('[data-testid="stepper"] [data-step="offer"] [data-part="caption"]');
const offerLink = (page: Page) => page.locator('[data-testid="stepper"] [data-step="offer"] a');
const picker = (page: Page) => page.getByTestId("chat-customer-select");

/** Approve the Tea play on the landing, then open /chat: the panel opens on Ravi. */
async function approveTeaThenChat(page: Page) {
  await openBeat(page);
  await page.getByTestId("approve-button").first().click();
  await approveSettled(page);
  await page.goto("/chat");
  await expect(picker(page)).toHaveValue("CUST-RAVI");
}

test.describe("chat persona: the line and the stepper follow the chat customer", () => {
  test("default, before any approve: Meena in both", async ({ page }) => {
    await page.goto("/chat");
    await expect(picker(page)).toHaveValue("CUST-MEENA");
    await expect(who(page)).toContainText("This screen is for Meena, customer");
    await expect(offerCaption(page)).toHaveText("Meena");
  });

  test("after the Tea approve the chat opens on Ravi: the line and the Offer sublabel read Ravi", async ({ page }) => {
    await approveTeaThenChat(page);
    await expect(page.locator("#chat-panel h3")).toHaveText("Chat as Ravi");
    await expect(who(page)).toContainText("This screen is for Ravi, customer");
    await expect(who(page).locator("svg text")).toHaveText("R");
    await expect(offerCaption(page)).toHaveText("Ravi");
    await expect(offerLink(page)).toHaveAttribute("aria-label", /^Offer: Chat \(Ravi\)/);
    // the chips still offer the other two screens, and not the person this screen is for
    const nav = page.getByTestId("persona-bar").getByRole("navigation", { name: "View as" });
    await expect(nav.getByRole("link")).toHaveCount(2);
  });

  test("switching the picker updates both, each time", async ({ page }) => {
    await approveTeaThenChat(page);
    await picker(page).selectOption("CUST-MEENA");
    await expect(who(page)).toContainText("This screen is for Meena, customer");
    await expect(offerCaption(page)).toHaveText("Meena");
    await picker(page).selectOption("CUST-RAVI");
    await expect(who(page)).toContainText("This screen is for Ravi, customer");
    await expect(offerCaption(page)).toHaveText("Ravi");
  });

  test("other routes keep their persona after the same approve", async ({ page }) => {
    await approveTeaThenChat(page);
    for (const [route, name, role] of [["/", "Arjun", "demand planner"], ["/desk", "Arjun", "demand planner"], ["/outcomes", "Arjun", "demand planner"], ["/phone", "Priya", "node manager"]]) {
      await page.goto(route);
      await expect(who(page)).toContainText(`This screen is for ${name}, ${role}`);
      await expect(offerCaption(page)).toHaveText("Meena");
    }
  });

  test("leaving /chat for another screen in the same session restores that screen's persona", async ({ page }) => {
    await approveTeaThenChat(page);
    await page.getByRole("link", { name: "View as Arjun, demand planner" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(who(page)).toContainText("This screen is for Arjun, demand planner");
    await expect(offerCaption(page)).toHaveText("Meena");
    await page.goBack();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(who(page)).toContainText("Ravi, customer");
  });
});

test.describe("chat persona: 375 px", () => {
  test.use({ viewport: { width: 375, height: 812 } });
  test("after the approve /chat shows Ravi and does not overflow sideways", async ({ page }) => {
    await approveTeaThenChat(page);
    await expect(who(page)).toContainText("Ravi");
    await expect(offerCaption(page)).toHaveText("Ravi");
    await assertNoHorizontalOverflow(page);
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`chat persona: axe (${scheme})`, () => {
    test.use({ colorScheme: scheme });
    test("/chat on Ravi has no violations", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await approveTeaThenChat(page);
      await expect(who(page)).toContainText("Ravi");
      await page.waitForTimeout(300);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  });
}
