import { test, expect } from "@playwright/test";
import { asVisitor, shot } from "./helpers";

// Screenshot-only capture for docs/screenshots/, against the real stack (see `make live-test`).
// The gap card's "days remaining" is computed client-side against the browser's wall clock, while
// the seeded demo data is dated relative to the server's TAAL_NOW; run this on any day other than
// the demo's own date and the two drift apart, which is exactly what happened here (the sandbox's
// real clock is well past the demo's TAAL_NOW=2026-09-12T03:30:00Z baseline). The rest of this repo
// (server, tests) is pinned by TAAL_NOW; to freeze the client's wall clock to the same value for
// screenshots, this spec overrides `Date` (not timers) via page.addInitScript. It duplicates just
// enough of judge.spec.ts / priya.spec.ts to reach each screen; the strict correctness assertions
// stay in those files.
const TAAL_NOW_MS = Date.parse("2026-09-12T03:30:00Z");

async function freezeClock(page: import("@playwright/test").Page) {
  await page.addInitScript((fixed) => {
    const OrigDate = Date;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
    // @ts-expect-error overriding the global on purpose, screenshot capture only
    window.Date = FixedDate;
  }, TAAL_NOW_MS);
}

test.describe("Screenshots: judge landing, approve, chat, reset", () => {
  test("capture judge-02..05", async ({ page }) => {
    await freezeClock(page);
    await asVisitor(page, "shots-judge");
    await page.goto("/");
    await expect(page.getByText("Taal judge mode")).toBeVisible();

    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const beat = page.getByTestId("beat-panel");
    await expect(beat.getByText("₹9,200")).toBeVisible();
    await expect(beat.getByText(/6 days|days/)).toBeVisible();
    await shot(page, "judge-02-gap-card");

    await beat.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await shot(page, "judge-03-approved-chart");

    const chat = page.getByTestId("chat-log");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(chat.getByText(/ಬಳಕೆಗೆ ಉತ್ತಮ|Best before/)).toBeVisible({ timeout: 15_000 });
    await shot(page, "judge-04-chat-offer");

    await page.getByRole("button", { name: "Reset demo data" }).click();
    await expect(page.getByRole("button", { name: "Reset demo data" })).toBeEnabled();
    await shot(page, "judge-05-after-reset");
  });
});

test.describe("Screenshots: Outcomes, settled", () => {
  test("capture mgmt-02-measured without the fade-in animation mid-flight", async ({ page }) => {
    await freezeClock(page);
    await asVisitor(page, "shots-mgmt");
    await page.goto("/outcomes");
    await expect(page.getByRole("heading", { name: "Outcomes" })).toBeVisible();

    const h = { "X-Taal-Visitor": "shots-mgmt", "Content-Type": "application/json" };
    const API = process.env.TAAL_API_URL || "http://localhost:8080";
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_chips_ds07_v1" } });
    await page.request.post(`${API}/approve`, { headers: h, data: { play_id: "play_kaju_ds03_v1" } });
    await page.request.post(`${API}/chat`, { headers: { ...h, Accept: "application/json" }, data: { session_id: "CUST-MEENA:web", text: "Any offers?" } });
    await page.request.post(`${API}/chat`, { headers: { ...h, Accept: "application/json" }, data: { session_id: "CUST-MEENA:web", text: "add:SKU-MASALA-CHIPS-200G" } });

    await page.getByRole("button", { name: "Run Measure" }).click();
    await expect(page.getByText(/measured, .* unmeasured/)).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(500); // let the row fade-in animation finish before the shot
    await shot(page, "mgmt-02-measured");
  });
});

test.describe("Screenshots: Priya phone intake, gap card, approve, execution", () => {
  test("capture priya-02..05", async ({ page }) => {
    await freezeClock(page);
    await asVisitor(page, "shots-priya");
    await page.goto("/phone");
    await expect(page.getByRole("heading", { name: "Priya's phone" })).toBeVisible();

    await page.getByRole("button", { name: "Pallet 1" }).click();
    const table = page.getByTestId("intake-table");
    await expect(table).toBeVisible();
    await shot(page, "priya-02-intake");

    // Pallet 1's current fixture (regenerated from a real Gemini read, see eval/evaluation.md's
    // 21 Sep vision-accuracy correction) reads all rows at high confidence, so no per-row "Yes"
    // confirmation is needed -- straight to "Confirm rows".
    const confirmed = page.waitForResponse((r) => r.url().endsWith("/capture/confirm"));
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await confirmed;
    await expect(page.getByText("₹9,200")).toBeVisible({ timeout: 15_000 });
    await shot(page, "priya-03-gap-card");

    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: "Execution steps" })).toBeVisible();
    await shot(page, "priya-04-approved");

    const labels = page.locator(".execution-steps label");
    const n = await labels.count();
    for (let i = 0; i < n; i++) await labels.nth(i).click();
    await page.getByRole("button", { name: "Done" }).click();
    await expect(page.getByText(/exec_play_chips_ds07_v1|Recorded|recorded/)).toBeVisible();
    await shot(page, "priya-05-execution");
  });
});
