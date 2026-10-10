import { test, expect } from "@playwright/test";
import { injectMockFaults } from "./helpers";

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

test.describe("customer chat: polish", () => {
  test("STOP is a labelled secondary button with an explanation, not an unlabelled red one", async ({ page }) => {
    await page.goto("/chat");
    const stop = page.getByRole("button", { name: "Customer replies STOP (opt-out demo)" });
    await expect(stop).toBeVisible();
    await expect(stop).toHaveAttribute("title", /opts out/);
    // at rest it is neutral: the page background, not the danger fill
    const bg = await stop.evaluate((el) => getComputedStyle(el).backgroundColor);
    const danger = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--danger").trim());
    expect(danger).not.toBe("");
    expect(bg).not.toBe("rgb(192, 54, 44)");
    await stop.click();
    await expect(page.getByTestId("chat-log").locator(".chat-msg--customer").last()).toHaveText("STOP");
  });

  test("the visitor's bubble is there at once as pending, then confirmed when the reply lands", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("taal_mock_delay", JSON.stringify({ "/chat": 1500 })));
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const mine = page.getByTestId("chat-log").locator(".chat-msg--customer");
    await expect(mine).toHaveText("Any offers today?");
    await expect(mine).toHaveAttribute("data-status", "pending");
    await expect(page.getByTestId("chat-log").locator(".chat-msg--agent").first()).toBeVisible({ timeout: 10_000 });
    await expect(mine).toHaveAttribute("data-status", "sent");
  });

  test("a failed send is marked not delivered, shows the error card inline, and Retry re-sends the same bubble", async ({ page }) => {
    await injectMockFaults(page, { "/chat": { kind: "network", times: 1 } });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log");
    await expect(log.getByTestId("error-card")).toBeVisible();
    await expect(log.locator(".chat-msg--customer")).toHaveAttribute("data-status", "failed");
    await log.getByRole("button", { name: "Retry" }).click();
    await expect(log.locator(".chat-msg--agent").first()).toBeVisible({ timeout: 10_000 });
    await expect(log.locator(".chat-msg--customer")).toHaveCount(1);
    await expect(log.locator(".chat-msg--customer")).toHaveAttribute("data-status", "sent");
    await expect(log.getByTestId("error-card")).toHaveCount(0);
  });

  test("Kannada text carries lang=kn; the English line opens for the first reply and Hide/Show English remembers the choice", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log");
    const offer = log.locator(".chat-msg--agent").first();
    await expect(offer.locator("p[lang='kn']")).toContainText("ಇಂದು");
    await expect(offer.getByTestId("english-gloss")).toBeVisible();
    await expect(offer.getByTestId("gloss-toggle")).toHaveText("Hide English");
    await offer.getByTestId("gloss-toggle").click();
    await expect(offer.getByTestId("english-gloss")).toHaveCount(0);
    await expect(offer.getByTestId("gloss-toggle")).toHaveText("Show English");
    await expect(offer.getByTestId("gloss-toggle")).toHaveAttribute("aria-expanded", "false");
    // the next Kannada reply starts the way the visitor left it (hidden)
    await offer.getByRole("button", { name: "Not now" }).click();
    await expect(log.locator(".chat-msg--agent")).toHaveCount(2, { timeout: 10_000 });
  });

  test("an English reply to a Kannada customer is labelled English fallback; the same reply to an English customer is not", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Do you have Cola Zero?" }).click();
    const log = page.getByTestId("chat-log");
    const reply = log.locator(".chat-msg--agent").last();
    await expect(reply.getByTestId("english-fallback-label")).toContainText("English fallback");
    await expect(reply.locator("p[lang='en']").first()).toBeVisible();

    await page.getByTestId("chat-customer-select").selectOption("CUST-RAVI");
    await page.getByRole("button", { name: "Do you have Cola Zero?" }).click();
    await expect(log.locator(".chat-msg--agent").last()).toBeVisible();
    await expect(log.getByTestId("english-fallback-label")).toHaveCount(0);
  });

  test("the picker reads 'Meena, Dark store 7 (Kannada)' with no ids; ids and sources sit inside Details", async ({ page }) => {
    await page.goto("/chat");
    const select = page.getByTestId("chat-customer-select");
    await expect(select.locator("option")).toHaveCount(3);
    const options = await select.locator("option").allTextContents();
    expect(options).toContain("Meena, Dark store 7 (Kannada)");
    expect(options.some((o) => /CUST-|DS-\d/.test(o))).toBe(false);
    expect(options.some((o) => o.includes("holdout"))).toBe(true);
    await expect(page.getByTestId("chat-customer-ids")).toContainText("CUST-MEENA");

    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log");
    await expect(log.locator(".chat-msg--agent").first()).toBeVisible();
    // the raw "cited: ..." line is gone; the refs are only inside the Sources disclosure
    await expect(log.getByText(/cited:/)).toHaveCount(0);
    await expect(log.getByTestId("chat-sources").first()).toContainText("Sources");
    await expect(log.getByTestId("chat-sources").first().locator("summary")).toHaveText("Sources");
  });

  test("duplicate quick-reply labels are shown once", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const offer = page.getByTestId("chat-log").locator(".chat-msg--agent").first();
    const labels = await offer.locator(".chat-msg__buttons button").allTextContents();
    expect(new Set(labels.map((l) => l.trim().toLowerCase())).size).toBe(labels.length);
  });
});
