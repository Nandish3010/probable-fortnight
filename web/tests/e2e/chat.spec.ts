import { test, expect } from "@playwright/test";

test.describe("customer chat", () => {
  test("a Kannada bubble carries an English gloss under it; an English reply does not", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click(); // pre-filled "Any offers today?"
    const log = page.getByTestId("chat-log");
    const offer = log.locator(".chat-msg--agent").first();
    await expect(offer).toContainText("ಇಂದು");
    await expect(offer.getByTestId("english-gloss")).toHaveText(/^English: Offer: Masala Chips 200G with Coconut Water 1L for ₹61/);

    await page.getByRole("button", { name: "Do you have Cola Zero?" }).click();
    const substitution = log.locator(".chat-msg--agent").last();
    await expect(substitution).toContainText("Cola Zero 500ML is out");
    await expect(substitution.getByTestId("english-gloss")).toHaveCount(0);
  });

  test("a quick-reply bubble shows the button label, not the internal action payload", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click(); // pre-filled "Any offers today?"
    const log = page.getByTestId("chat-log");
    const offer = log.locator(".chat-msg--agent").first();
    await offer.getByRole("button", { name: "Add to cart" }).click();

    await expect(log.locator(".chat-msg--customer").last()).toHaveText("Add to cart");
    await expect(log.getByText(/add:SKU/)).toHaveCount(0);
    // the reply to the click still arrives (the mock routes the unchanged payload to its order scenario)
    await expect(log.locator(".chat-msg--agent")).toHaveCount(2);
  });
});
