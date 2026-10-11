import { test, expect, type Page } from "@playwright/test";
import { API, SHOTS, asVisitor, visitorHeaders } from "./helpers";

// Frames for deck slides 6 (trace attempts + chat) and 10 (phone confirm + Outcomes), captured from the
// redesigned UI against the local stack (see `make live-test`). Written next to the other live
// screenshots in eval/runs/screens; the owner copies them into the deck folders.
const TAAL_NOW_MS = Date.parse("2026-09-12T03:30:00Z");

async function prepare(page: Page) {
  await page.addInitScript((fixed) => {
    const OrigDate = Date;
    class FixedDate extends OrigDate {
      constructor(...args: unknown[]) {
        if (args.length === 0) super(fixed);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        else super(...(args as any));
      }
      static now() {
        return fixed;
      }
    }
    // @ts-expect-error screenshot capture only: freeze the client clock to the demo date
    window.Date = FixedDate;
    document.addEventListener("DOMContentLoaded", () => {
      const style = document.createElement("style");
      style.textContent = "nextjs-portal { display: none !important; }";
      document.head.appendChild(style);
    });
  }, TAAL_NOW_MS);
  await page.emulateMedia({ reducedMotion: "reduce" });
}

test.use({ deviceScaleFactor: 2 });

test.describe("Deck frames", () => {
  test("the landing with the loop diagram (docs/screenshots/judge-mode-landing.png)", async ({ page }) => {
    await prepare(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    await asVisitor(page, "deck-landing");
    await page.goto("/");
    await expect(page.getByTestId("loop-diagram")).toBeVisible();
    await expect(page.getByTestId("chat-customer-select")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/landing-loop.png`, fullPage: true });
  });

  test("slide 6: the guardrail-attempts trace with the model chip, no raw run id", async ({ page }) => {
    await prepare(page);
    await asVisitor(page, "deck-trace");
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const trace = page.getByTestId("play-detail").locator(".trace-panel").first();
    await expect(trace.getByTestId("trace-attempts")).toBeVisible();
    await expect(trace.getByTestId("model-chip")).toBeVisible();
    await expect(trace.locator(".trace-panel__header")).not.toContainText(/run_/);
    await trace.getByTestId("trace-attempts").scrollIntoViewIfNeeded();
    const header = trace.locator(".trace-panel__header");
    const attempts = trace.getByTestId("trace-attempts");
    const hb = (await header.boundingBox())!;
    const ab = (await attempts.boundingBox())!;
    await page.screenshot({
      path: `${SHOTS}/slide06-trace.png`,
      clip: { x: Math.max(0, Math.min(hb.x, ab.x) - 8), y: hb.y - 8, width: Math.max(hb.width, ab.width) + 16, height: ab.y + ab.height - hb.y + 16 },
    });
    await page.screenshot({ path: `${SHOTS}/slide06-desk-full.png`, fullPage: true });
  });

  test("slide 6: the customer chat after the chips approve", async ({ page }) => {
    await prepare(page);
    await page.setViewportSize({ width: 760, height: 960 });
    const vid = "deck-chat";
    await asVisitor(page, vid);
    await page.request.post(`${API}/approve`, { headers: visitorHeaders(vid), data: { play_id: "play_chips_ds07_v1" } });
    await page.goto("/chat");
    const log = page.getByTestId("chat-log");
    // A Kannada question (code-mixed, as customers write): the reply comes back in Kannada with an English gloss.
    await page.getByPlaceholder("Type a message…").fill("ನಮಸ್ಕಾರ, ಇಂದು ಯಾವುದಾದರೂ offers ಇದೆಯೇ?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(log.getByText(/₹50ಕ್ಕೆ/)).toBeVisible({ timeout: 15_000 });
    await expect(log.getByText(/for ₹50\b/)).toBeVisible();
    await page.locator(".chat-panel").screenshot({ path: `${SHOTS}/slide06-chat.png` });
  });

  test("slide 10: the phone confirm question and the Outcomes screen", async ({ page }) => {
    await prepare(page);
    await page.setViewportSize({ width: 412, height: 915 });
    await asVisitor(page, "deck-phone");
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 6" }).click();
    const table = page.getByTestId("intake-table");
    await expect(table).toBeVisible();
    await expect(table.locator(".confirm-row")).toBeVisible();
    await page.waitForTimeout(500); // thumbnails
    // A full-page capture would paint the sticky top bar in the middle of the page: put it back in the flow.
    await page.addStyleTag({ content: ".top-nav { position: static !important; }" });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${SHOTS}/slide10-phone.png`, fullPage: true });

    await page.setViewportSize({ width: 1280, height: 900 });
    const vid = "deck-outcomes";
    await asVisitor(page, vid);
    await page.goto("/outcomes");
    await expect(page.getByRole("heading", { name: "Outcomes", level: 1 })).toBeVisible();
    const h = visitorHeaders(vid);
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_chips_ds07_v1" } });
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_kaju_ds03_v1" } });
    await page.request.post(`${API}/chat`, { headers: { ...h, Accept: "application/json" }, data: { session_id: "CUST-MEENA:web", text: "Any offers?" } });
    await page.request.post(`${API}/chat`, { headers: { ...h, Accept: "application/json" }, data: { session_id: "CUST-MEENA:web", text: "add:SKU-MASALA-CHIPS-200G" } });
    await page.getByRole("button", { name: "Run Measure" }).click();
    await expect(page.getByText(/measured, .* unmeasured/)).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${SHOTS}/slide10-outcomes.png`, fullPage: true });
  });
});
