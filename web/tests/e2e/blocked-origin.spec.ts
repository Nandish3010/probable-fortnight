import fs from "node:fs";
import path from "node:path";
import { test, expect, type Page, type Route } from "@playwright/test";
import { forceLiveApi } from "./helpers";

// The REAL request wrapper (lib/api.ts), in a browser. forceLiveApi() switches the mock-mode dev
// server onto the real request path and points it at http://127.0.0.1:59999, where nothing
// listens: a blocked or dead origin. These tests prove the Landing beat and the Desk show the
// ErrorCard within 10 s instead of a spinner, and that a 503 / 409 on the wire maps to the right
// card. (The mock-mode suites inject the same failures without a network.)

const API = "http://127.0.0.1:59999";
const mock = (name: string) => JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../mocks", `${name}.json`), "utf-8"));

const CORS = {
  "access-control-allow-origin": `http://localhost:${process.env.PORT || 3100}`,
  "access-control-allow-credentials": "true",
  "access-control-allow-headers": "content-type, x-taal-visitor",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-expose-headers": "retry-after",
};

type Handler = (route: Route) => Promise<void> | void;

/** A tiny fake API on the unreachable origin: answers CORS preflights and the listed paths. */
async function fakeApi(page: Page, handlers: Record<string, Handler>) {
  await page.route(`${API}/**`, async (route) => {
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
const ok = (body: unknown): Handler => (route) => route.fulfill({ status: 200, headers: CORS, contentType: "application/json", body: JSON.stringify(body) });
const status = (code: number, body: unknown, extra: Record<string, string> = {}): Handler => (route) =>
  route.fulfill({ status: code, headers: { ...CORS, ...extra }, contentType: "application/json", body: JSON.stringify(body) });

test.beforeEach(async ({ page }) => {
  await forceLiveApi(page, API);
});

test.describe("a blocked origin (nothing listens on the API address)", () => {
  test("Landing: the beat shows the card within 10 s, not a spinner; Show recorded result still works", async ({ page }) => {
    await page.goto("/");
    const started = Date.now();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toBeVisible({ timeout: 10_000 });
    expect(Date.now() - started).toBeLessThan(10_000);
    await expect(card).toHaveAttribute("role", "alert");
    await expect(card).toContainText("Can't reach the Taal service");
    await expect(card).toContainText("The demo server isn't answering. This usually clears in a minute.");
    await expect(card.getByRole("button", { name: "Retry" })).toBeEnabled();
    await expect(page.getByText("Loading gap and play…")).toHaveCount(0);

    await card.getByRole("button", { name: "Show recorded result" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("recorded-note")).toContainText("REPLAY");
  });

  test("Landing: the footer health strip also says the service is unavailable", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".health-strip--error")).toHaveText("Health check unavailable.", { timeout: 10_000 });
  });

  test("Desk: the inbox shows the card within 10 s, with Retry and Show recorded result", async ({ page }) => {
    await page.goto("/desk");
    const card = page.getByTestId("error-card").first();
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card).toContainText("Can't reach the Taal service");
    await expect(page.getByText("Loading plays…")).toHaveCount(0);
    await card.getByRole("button", { name: "Show recorded result" }).click();
    await expect(page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first()).toBeVisible();
    await expect(page.getByTestId("recorded-note")).toContainText("REPLAY");
  });

  test("Outcomes: the table area shows the card instead of 'Loading…'", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByRole("button", { name: "Show recorded result" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Loading…", { exact: true })).toHaveCount(0);
  });
});

test.describe("failures on the wire", () => {
  test("a server that never answers: 'taking longer than expected' by the 10 s budget", async ({ page }) => {
    test.setTimeout(30_000);
    await fakeApi(page, {
      "/health": ok(mock("health")),
      "/plays": ok(mock("plays")),
      "/gaps": () => new Promise<void>(() => {}), // never fulfilled
    });
    await page.goto("/");
    const started = Date.now();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toBeVisible({ timeout: 13_000 });
    await expect(card).toContainText("This is taking longer than expected");
    const elapsed = Date.now() - started;
    expect(elapsed).toBeGreaterThanOrEqual(9_000);
    expect(elapsed).toBeLessThan(12_500);
  });

  test("503 model_unavailable with Retry-After on /chat: the card names the wait and Retry unlocks after it", async ({ page }) => {
    await fakeApi(page, {
      "/health": ok(mock("health")),
      "/customers/demo": ok(mock("customers_demo")),
      "/chat": status(503, { error: "model_unavailable", model: "gemini-3.5-flash", retry_after_s: 3 }, { "retry-after": "3" }),
    });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const card = page.getByTestId("error-card");
    await expect(card).toContainText("The AI model is busy");
    await expect(card).toContainText("Try again in 3 seconds");
    await expect(card.getByRole("button", { name: /Retry/ })).toBeDisabled();
    await expect(card.getByRole("button", { name: "Retry" })).toBeEnabled({ timeout: 6_000 });
  });

  test("409 on /approve shows the recorded result with the 'Already approved' banner", async ({ page }) => {
    await fakeApi(page, {
      "/health": ok(mock("health")),
      "/gaps": ok(mock("gaps")),
      "/plays": ok(mock("plays")),
      "/approve": status(409, { detail: "x" }),
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByTestId("already-approved-banner")).toHaveText("Already approved. Showing the recorded result.");
  });

  test("404 on /approve: 'This demo session was restarted', and no Retry that cannot help", async ({ page }) => {
    await fakeApi(page, {
      "/health": ok(mock("health")),
      "/gaps": ok(mock("gaps")),
      "/plays": ok(mock("plays")),
      "/approve": status(404, { detail: "x" }),
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByTestId("approve-error")).toContainText("This demo session was restarted");
    await expect(page.getByTestId("approve-error").getByRole("button", { name: "Retry" })).toHaveCount(0);
  });

  test("a double-clicked Approve sends exactly one POST over the wire", async ({ page }) => {
    let posts = 0;
    await fakeApi(page, {
      "/health": ok(mock("health")),
      "/gaps": ok(mock("gaps")),
      "/plays": ok(mock("plays")),
      "/approve": async (route) => {
        posts += 1;
        await new Promise((r) => setTimeout(r, 600));
        await ok(mock("approve"))(route);
      },
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByRole("button", { name: "Approve" }).dblclick();
    await expect(page.getByTestId("approve-result")).toBeVisible({ timeout: 15_000 });
    expect(posts).toBe(1);
  });
});
