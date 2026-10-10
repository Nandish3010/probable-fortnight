import { expect, type Locator, type Page } from "@playwright/test";

/** The page must not scroll sideways: the document is no wider than the viewport. */
export async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth, `document is ${scrollWidth}px wide in a ${clientWidth}px viewport`).toBeLessThanOrEqual(clientWidth);
}

export type MockFaultKind = "network" | "timeout" | "http" | "model_unavailable" | "conflict" | "not_found" | "rate_limited";

export interface MockFaultSpec {
  kind: MockFaultKind;
  retry_after_s?: number;
  /** Fail this many calls, then behave normally. Omit to fail every call. */
  times?: number;
}

/** Mock-mode fault injection (web/lib/mockFaults.ts): keys are path prefixes such as "/chat". Set
 * before any page script runs. Cleared with localStorage when the context ends. */
export async function injectMockFaults(page: Page, faults: Record<string, MockFaultSpec>): Promise<void> {
  await page.addInitScript((f) => {
    try {
      // Only on first load of a page: a reload must not reset the remaining `times`.
      if (!window.sessionStorage.getItem("taal_fault_installed")) {
        window.localStorage.setItem("taal_mock_fault", JSON.stringify(f));
        window.sessionStorage.setItem("taal_fault_installed", "1");
      }
    } catch {
      // Storage blocked: the test will fail on its own assertion.
    }
  }, faults);
}

/** How many times a mocked route was called in this page (window.__taalMockCalls). */
export async function mockCalls(page: Page, path: string): Promise<number> {
  return page.evaluate((p) => (window as unknown as { __taalMockCalls?: Record<string, number> }).__taalMockCalls?.[p] ?? 0, path);
}

/** Stops injecting faults on the already-loaded page, so the next Retry succeeds. (A fault with
 * `times` is unreliable for reads made in a useEffect: React's dev-mode double effect run uses
 * the first call up before the user ever sees it.) */
export async function clearMockFaults(page: Page): Promise<void> {
  await page.evaluate(() => window.localStorage.removeItem("taal_mock_fault"));
}

/** Runs the app's REAL request path (lib/api.ts apiFetch) against `apiUrl` instead of the mock
 * fixtures (see liveOverride in lib/api.ts). Point it at an address nothing listens on for a blocked
 * origin, or at one that page.route() answers for a fake API. */
export async function forceLiveApi(page: Page, apiUrl: string): Promise<void> {
  await page.addInitScript((url) => {
    try {
      window.localStorage.setItem("taal_force_live", "1");
      window.localStorage.setItem("taal_api_url", url);
    } catch {
      // Storage blocked: the test will fail on its own assertion.
    }
  }, apiUrl);
}

// ---------- a fake API on an unreachable origin (the real request path, answered by page.route) ----------

import fs from "node:fs";
import path from "node:path";
import type { Route } from "@playwright/test";

export const FAKE_API = "http://127.0.0.1:59999";

export const mockFixture = (name: string) =>
  JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../mocks", `${name}.json`), "utf-8"));

const CORS = {
  "access-control-allow-origin": `http://localhost:${process.env.PORT || 3100}`,
  "access-control-allow-credentials": "true",
  "access-control-allow-headers": "content-type, x-taal-visitor",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-expose-headers": "retry-after",
};

export type FakeHandler = (route: Route) => Promise<void> | void;

/** Answers CORS preflights and the listed paths on FAKE_API; anything else is a 404. */
export async function fakeApi(page: Page, handlers: Record<string, FakeHandler>): Promise<void> {
  await page.route(`${FAKE_API}/**`, async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }
    const handler = handlers[new URL(req.url()).pathname];
    if (handler) await handler(route);
    else await route.fulfill({ status: 404, headers: CORS, contentType: "application/json", body: "{}" });
  });
}

export const okJson =
  (body: unknown): FakeHandler =>
  (route) =>
    route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });

/** The handlers every landing-beat test on the fake API needs. */
export function beatHandlers(extra: Record<string, FakeHandler> = {}): Record<string, FakeHandler> {
  return {
    "/health": okJson(mockFixture("health")),
    "/gaps": okJson(mockFixture("gaps")),
    "/plays": okJson(mockFixture("plays")),
    "/customers/demo": okJson(mockFixture("customers_demo")),
    ...extra,
  };
}

/** Slows mocked routes (mock mode): {"/approve": 4000, "/chat": 9000}. See lib/mockFaults.ts. */
export async function setMockDelay(page: Page, delays: Record<string, number>): Promise<void> {
  await page.addInitScript((d) => {
    try {
      window.localStorage.setItem("taal_mock_delay", JSON.stringify(d));
    } catch {
      // Storage blocked: the test will fail on its own assertion.
    }
  }, delays);
}

/** Waits until the Approve result has finished its sequence (or is the recorded one). */
export async function approveSettled(page: Page): Promise<void> {
  await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
}

/** Opens the landing's first decision card. From 768 px up that takes the 60-second beat button; on
 * a phone the landing is the feed and its first card is already there. Returns the card's wrapper,
 * so a test can scope to it (on a phone the page holds three cards, and so three Approve buttons). */
export async function openBeat(page: Page, opts: { goto?: boolean } = {}): Promise<Locator> {
  if (opts.goto !== false) await page.goto("/");
  const width = page.viewportSize()?.width ?? 1280;
  if (width < 768) {
    const card = page.getByTestId("feed-item-1");
    await expect(card.getByTestId("feed-card-1")).toBeVisible();
    return card;
  }
  await page.getByRole("button", { name: "Run the 60-second beat" }).click();
  const beat = page.getByTestId("beat-panel");
  await expect(beat).toBeVisible();
  return beat;
}

/** Makes the mock server forget what was approved, as a restarted demo server would. */
export async function forgetMockApprovals(page: Page): Promise<void> {
  await page.evaluate(() => window.localStorage.removeItem("taal_mock_approved"));
}
