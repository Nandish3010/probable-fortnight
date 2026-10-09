import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

// The order a customer places by accepting an offer must cost exactly what the offer said (the
// "total is Rs 30" regression: the clicked sku alone, at list). Three numbers have to agree: the
// bundle price on the approved play, the price in the offer bubble the customer was shown, and the
// total on the receipt after "Add to cart".
const numbers = (s: string) => (s.match(/\d+(?:\.\d+)?/g) ?? []).map(Number);

test.describe("order total equals the offered price", () => {
  test("accept the chips bundle offer in chat: the receipt total is the offered price", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-order-total";
    await asVisitor(page, vid);

    const approve = await page.request.post(`${API}/approve`, { headers: visitorHeaders(vid), data: { play_id: "play_chips_ds07_v1" } });
    expect(approve.ok()).toBeTruthy();
    const play = await (await page.request.get(`${API}/plays/play_chips_ds07_v1`, { headers: visitorHeaders(vid) })).json();
    expect(play.mechanic).toBe("bundle");
    const offered = Number(play.mechanic_params.bundle_price);
    expect(offered).toBeGreaterThan(0);

    await page.goto("/chat");
    const log = page.getByTestId("chat-log");
    await page.getByPlaceholder("Type a message…").fill("Any offers today?");
    await page.getByRole("button", { name: "Send" }).click();
    const offer = log.locator(".chat-msg--agent").filter({ hasText: String(offered) }).last();
    await expect(offer).toBeVisible({ timeout: 30_000 });
    expect(numbers(await offer.innerText())).toContain(offered); // the price shown to the customer

    // The quick-reply posts its payload (add:<sku>) unchanged, but the visitor's bubble shows the button's label.
    const addButton = offer.locator(".chat-msg__buttons button").first(); // "Add to cart" (add:<sku>)
    const label = (await addButton.innerText()).trim();
    const chatPost = page.waitForRequest((r) => r.url().endsWith("/chat") && r.method() === "POST");
    await addButton.click();
    expect(JSON.parse((await chatPost).postData() ?? "{}").text).toMatch(/^add:SKU-/);
    const mine = log.locator(".chat-msg--customer");
    await expect(mine.last()).toHaveText(label);
    await expect(log.getByText(/add:SKU-/)).toHaveCount(0);
    const receipt = log.locator(".chat-msg--agent").filter({ hasText: /ORD-/ }).last();
    await expect(receipt).toBeVisible({ timeout: 30_000 });
    const text = await receipt.locator("p").first().innerText();
    const total = text.match(/(?:total is|ಒಟ್ಟು)\s*₹\s*(\d+(?:\.\d+)?)/);
    expect(total, `no total in the receipt: ${text}`).not.toBeNull();
    expect(Number(total![1])).toBe(offered);
    await shot(page, "order-total-receipt");
    await expectNoConsoleErrors(errors);
  });
});
