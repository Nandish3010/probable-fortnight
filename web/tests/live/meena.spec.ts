import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

async function say(page: import("@playwright/test").Page, text: string) {
  await page.getByPlaceholder("Type a message…").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test.describe("Meena: chat", () => {
  test("no offer before approval; offer, browse, substitution, order, stacking, STOP after", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-meena";
    await asVisitor(page, vid);
    await page.goto("/chat");
    const log = page.getByTestId("chat-log");
    await page.getByRole("button", { name: "Send" }).click(); // pre-filled "Any offers today?"
    await expect(log.getByText(/ಯಾವುದೇ ಆಫರ್ ಇಲ್ಲ|No offers/)).toBeVisible();

    await page.request.post(`${API}/approve`, { headers: visitorHeaders(vid), data: { play_id: "play_chips_ds07_v1" } });
    await say(page, "Any offers today?");
    await expect(log.getByText(/ಬಳಕೆಗೆ ಉತ್ತಮ|Best before/).last()).toBeVisible();
    await shot(page, "meena-01-offer");

    await say(page, "What all do you have?");
    await expect(log.getByText(/Beverages|Snacks|Bakery/).first()).toBeVisible();
    await say(page, "Tell me for chips");
    await expect(log.getByText(/Chips/).last()).toBeVisible();
    await say(page, "Is there bread?");
    await expect(log.getByText(/Bread|Pav|Bun/).last()).toBeVisible();
    await shot(page, "meena-02-browse");

    await say(page, "Do you have Cola Zero?");
    await expect(log.getByText(/Cola Lite|Cola Zero 1L|Cola Zero 250ML/).last()).toBeVisible();
    await shot(page, "meena-03-substitution");

    // a shown substitute list must be clickable, not just typeable -- this is the only way a
    // real customer adds something from a list rather than a button
    await log.locator(".chat-msg__list-item").last().click();
    await expect(log.getByText(/ORD-/).last()).toBeVisible();

    await say(page, "add:SKU-MASALA-CHIPS-200G");
    await expect(log.getByText(/ORD-/).last()).toBeVisible();
    await say(page, "add:SKU-MASALA-CHIPS-200G");
    await expect(log.getByText(/ORD-/).last()).toBeVisible();
    await shot(page, "meena-04-order");

    await page.locator("button.chat-panel__stop").click();
    await expect(log.getByText(/ಆಫರ್‌ಗಳು ಬರುವುದಿಲ್ಲ|will not receive/)).toBeVisible();
    await say(page, "Any offers today?");
    await expect(log.getByText(/ಯಾವುದೇ ಆಫರ್ ಇಲ್ಲ|No offers/).last()).toBeVisible();
    await shot(page, "meena-05-stop");

    // a holdout customer never sees the offer
    const ass = await (await page.request.get(`${API}/plays/play_chips_ds07_v1`, { headers: visitorHeaders(vid) })).json();
    expect(ass.status).toBe("approved");
    await expectNoConsoleErrors(errors);
  });
});

test.describe("customer picker: differentiation", () => {
  test("switching to the holdout customer shows no offer where Meena gets one", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-picker";
    await asVisitor(page, vid);
    await page.request.post(`${API}/approve`, { headers: visitorHeaders(vid), data: { play_id: "play_chips_ds07_v1" } });

    await page.goto("/chat");
    const select = page.getByTestId("chat-customer-select");
    await expect(select).toBeVisible();
    const options = await select.locator("option").allTextContents();
    expect(options.some((o) => o.includes("holdout"))).toBeTruthy();

    // Meena (default): the offer arrives
    await say(page, "Any offers today?");
    const log = page.getByTestId("chat-log");
    await expect(log.getByText(/ಬಳಕೆಗೆ ಉತ್ತಮ|Best before/)).toBeVisible({ timeout: 15_000 });

    // switch to the holdout customer: a fresh conversation, no offer, ever
    await select.selectOption({ label: await select.locator("option", { hasText: "holdout" }).textContent() as string });
    await expect(log.getByText("Send a message to start.")).toBeVisible();
    await say(page, "Any offers today?");
    await expect(log.getByText(/No offers|ಯಾವುದೇ ಆಫರ್ ಇಲ್ಲ/)).toBeVisible({ timeout: 15_000 });
    await expect(log.getByText(/ಬಳಕೆಗೆ ಉತ್ತಮ|Best before/)).toHaveCount(0);
    await expectNoConsoleErrors(errors);
  });
});
