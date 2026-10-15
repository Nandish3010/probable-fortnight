import { test, expect, type Page } from "@playwright/test";
import { errorFromResponse } from "../../lib/apiError";
import { errorCopy } from "../../lib/errorCopy";
import { FAKE_API, beatHandlers, fakeApi, forceLiveApi, injectMockFaults, mockCalls, mockFixture, okJson, type FakeHandler } from "./helpers";

// A 429 from the API is a spend cap, not a bug: the visitor is told which cap, for how long to wait, sees
// the wait run down on the Retry button, and can retry the moment it ends. Two caps exist on the API
// (services/api/main.py _rate_limit): the shared, process-wide cap ("demo capacity: ...") and the
// per-visitor one ("rate limit: ..."). It applies to Plan live, chat and the phone photo upload (the
// sample pallets replay recorded reads and are never limited); a 503 model_unavailable is unchanged.

const SHARED_DETAIL = "demo capacity: the shared limit of 120 plan calls per 15 minutes is reached; try again in about 240 seconds";
const VISITOR_DETAIL = "rate limit: at most 20 plan calls per 900s per visitor; wait and retry";
const SHARED_BODY = (s: number) => `The demo is busy right now (shared usage limit). Please wait about ${s} seconds and try again.`;
const VISITOR_BODY = (s: number) => `You have used the limit for this feature. Please wait about ${s} seconds.`;

test.describe("429 copy (pure)", () => {
  test("the scope comes from the detail text, and the seconds from Retry-After first", () => {
    const shared = errorFromResponse("/rerun", 429, { detail: SHARED_DETAIL }, "30");
    expect(shared.kind).toBe("rate_limited");
    expect(shared.rateScope).toBe("shared");
    expect(shared.retryAfterSeconds).toBe(30);
    const visitor = errorFromResponse("/chat", 429, { detail: VISITOR_DETAIL }, "45");
    expect(visitor.rateScope).toBe("visitor");
    expect(visitor.retryAfterSeconds).toBe(45);
    const unknown = errorFromResponse("/chat", 429, {}, "9");
    expect(unknown.rateScope).toBeUndefined();
    // a 429 body that is not JSON, or has no detail, still maps to rate_limited
    expect(errorFromResponse("/chat", 429, null, null).kind).toBe("rate_limited");
  });

  test("exact wording per scope; an unknown scope still tells the wait; 503 is unchanged", () => {
    const e = (scope: "shared" | "visitor" | undefined, s?: number) => errorFromResponse("/chat", 429, { detail: scope === "shared" ? SHARED_DETAIL : scope === "visitor" ? VISITOR_DETAIL : "" }, s === undefined ? null : String(s));
    expect(errorCopy(e("shared", 30)).body).toBe(SHARED_BODY(30));
    expect(errorCopy(e("visitor", 30)).body).toBe(VISITOR_BODY(30));
    expect(errorCopy(e(undefined, 9)).body).toBe("Please wait about 9 seconds and try again.");
    expect(errorCopy(e(undefined, 9)).title).toBe("Too many requests");
    expect(errorCopy(e("shared", 30)).title).toBe("The demo is busy");
    expect(errorCopy(e("visitor", 30)).title).toBe("Feature limit reached");
    expect(errorCopy(e(undefined)).body).toBe("Please wait a moment and try again.");
    const m = errorFromResponse("/chat", 503, { error: "model_unavailable", retry_after_s: 30 }, null);
    expect(errorCopy(m)).toEqual({ title: "The AI model is busy", body: "The model that writes the replies is overloaded right now. Try again in 30 seconds." });
  });
});

/** A card whose Retry waits out the seconds, then works. */
async function expectCountdownThenRetry(page: Page, seconds: number, body: string) {
  const card = page.getByTestId("error-card").first();
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("role", "alert");
  await expect(card).toHaveAttribute("data-error-kind", "rate_limited");
  await expect(card).toContainText(body);
  const retry = card.getByRole("button", { name: /Retry/ });
  await expect(retry).toBeDisabled();
  await expect(retry).toHaveText(new RegExp(`^Retry in [1-${seconds}] s$`)); // the countdown is on the button
  await expect(retry).toBeEnabled({ timeout: (seconds + 4) * 1000 });
  await expect(retry).toHaveText("Retry");
  return retry;
}

test.describe("429 on Plan live (Play Desk), 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  for (const [name, scope, body] of [
    ["shared cap", "shared", SHARED_BODY(2)],
    ["per-visitor cap", "visitor", VISITOR_BODY(2)],
  ] as const) {
    test(`${name}: the card says so, counts down, then Retry runs the plan`, async ({ page }) => {
      await injectMockFaults(page, { "/rerun": { kind: "rate_limited", retry_after_s: 2, scope, times: 1 } });
      await page.goto("/desk");
      await expect(page.getByTestId("play-detail")).toBeVisible();
      await page.getByTestId("plan-live").click();
      const retry = await expectCountdownThenRetry(page, 2, body);
      expect(await mockCalls(page, "/rerun")).toBe(1);
      await retry.click();
      await expect.poll(() => mockCalls(page, "/rerun")).toBe(2);
      await expect(page.getByTestId("error-card")).toHaveCount(0);
    });
  }
});

test.describe("429 in chat, 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("shared cap in mock mode: countdown, then Retry sends the same message once", async ({ page }) => {
    await injectMockFaults(page, { "/chat": { kind: "rate_limited", retry_after_s: 2, scope: "shared", times: 1 } });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const retry = await expectCountdownThenRetry(page, 2, SHARED_BODY(2));
    await retry.click();
    await expect(page.getByTestId("chat-log").locator(".chat-msg--agent").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("chat-log").locator(".chat-msg--customer")).toHaveCount(1);
    await expect(page.getByTestId("error-card")).toHaveCount(0);
  });

  test("the real request path: the API's own 429 (detail + Retry-After) picks the wording", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    let calls = 0;
    const limited = (detail: string): FakeHandler => async (route) => {
      calls += 1;
      await route.fulfill({
        status: 429,
        headers: {
          "access-control-allow-origin": `http://localhost:${process.env.PORT || 3100}`,
          "access-control-allow-credentials": "true",
          "access-control-expose-headers": "retry-after",
          "retry-after": "2",
        },
        contentType: "application/json",
        body: JSON.stringify({ detail }),
      });
    };
    await fakeApi(page, beatHandlers({ "/chat": limited(VISITOR_DETAIL) }));
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    await expectCountdownThenRetry(page, 2, VISITOR_BODY(2));
    expect(calls).toBe(1); // nothing was retried by itself
  });

  test("a second 429 starts the countdown again (Retry is not open at once)", async ({ page }) => {
    await injectMockFaults(page, { "/chat": { kind: "rate_limited", retry_after_s: 2, scope: "shared" } }); // every call fails
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const retry = await expectCountdownThenRetry(page, 2, SHARED_BODY(2));
    await retry.click();
    const again = page.getByTestId("error-card").first().getByRole("button", { name: /Retry/ });
    await expect(again).toBeDisabled();
    await expect(again).toHaveText(/^Retry in [1-2] s$/);
  });
});

test.describe("the sample pallets and the API's sample-sized reads are not limited", () => {
  test("a page that never calls the capped endpoints never shows a 429 card", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(page, beatHandlers({ "/outcomes": okJson(mockFixture("outcomes")) }));
    await page.goto("/");
    await expect(page.getByTestId("error-card")).toHaveCount(0);
  });
});
