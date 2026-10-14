import { test, expect, type Page } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, type FakeHandler } from "./helpers";

// A cold service answers its first reads late. On a 375 px phone no screen is ever an empty pane while
// it waits: the page shows its own heading and a loading line from the first frame, "Waking the demo"
// joins after about 1.5 s (wording unchanged: no seconds estimate, since no cold-start time is measured),
// and the data replaces both. The fake API answers every first read after COLD_MS.

const COLD_MS = 4500;
const WAKING = /Waking the demo\. It sleeps when idle, so the first load can take a little longer\. Nothing is wrong\./;

const late = (name: string): FakeHandler => async (route) => {
  await new Promise((r) => setTimeout(r, COLD_MS));
  await okJson(mockFixture(name))(route);
};

async function coldService(page: Page) {
  await page.setViewportSize({ width: 375, height: 812 });
  await forceLiveApi(page, FAKE_API);
  await fakeApi(
    page,
    beatHandlers({
      "/gaps": late("gaps"),
      "/plays": late("plays"),
      "/customers/demo": late("customers_demo"),
      "/health": late("health"),
    }),
  );
}

/** The page's main pane carries real words (not just chrome) and nothing scrolls sideways. */
async function paneIsNotEmpty(page: Page, minChars = 40) {
  const text = await page.locator("main").evaluate((m) => (m as HTMLElement).innerText.trim());
  expect(text.length).toBeGreaterThan(minChars);
  await assertNoHorizontalOverflow(page);
}

test.describe("cold start at 375 px: never an empty pane", () => {
  test("landing: the heading and the feed placeholder from the first frame, the notice after 1.5 s, then the feed", async ({ page }) => {
    await coldService(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("feed-loading")).toBeVisible();
    await expect(page.getByTestId("loop-strip")).toBeVisible();
    await paneIsNotEmpty(page, 200);
    await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3500 });
    await expect(page.getByTestId("waking-notice")).toContainText(WAKING);
    await expect(page.getByTestId("feed-loading")).toBeVisible();
    await paneIsNotEmpty(page, 200);
    await expect(page.getByTestId("decision-feed")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("waking-notice")).toHaveCount(0);
  });

  test("Desk: the heading and 'Loading plays…' from the first frame, the notice after 1.5 s, then the inbox", async ({ page }) => {
    await coldService(page);
    await page.goto("/desk");
    await expect(page.getByRole("heading", { name: "Play Desk" })).toBeVisible();
    await expect(page.getByText("Loading plays…")).toBeVisible();
    await paneIsNotEmpty(page);
    await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3500 });
    await expect(page.getByText("Loading plays…")).toBeVisible();
    await paneIsNotEmpty(page);
    await expect(page.getByLabel("Play inbox")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("waking-notice")).toHaveCount(0);
  });

  test("phone capture page: it needs no first read, so its form is there at once", async ({ page }) => {
    await coldService(page);
    await page.goto("/phone");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await paneIsNotEmpty(page, 200);
  });

  test("chat: 'Loading customers…' from the first frame, the notice after 1.5 s, then the picker", async ({ page }) => {
    await coldService(page);
    await page.goto("/chat");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("chat-customers-loading")).toBeVisible();
    await paneIsNotEmpty(page, 100);
    await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3500 });
    await expect(page.getByTestId("chat-customers-loading")).toBeVisible();
    await paneIsNotEmpty(page, 100);
    await expect(page.getByTestId("chat-customer-select")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("waking-notice")).toHaveCount(0);
  });

  test("the notice keeps its wording: no seconds estimate", async ({ page }) => {
    await coldService(page);
    await page.goto("/");
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toBeVisible({ timeout: 3500 });
    await expect(notice).not.toContainText(/\d/);
    await expect(notice).not.toContainText(/about \d+ ?s|seconds/i);
  });
});
