import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { chipModel, modelInfoFromHealth, planLiveEvalText, showsModelChip } from "../../lib/health";
import { injectMockFaults } from "./helpers";

// U.1 items: pass-rate chip, loop diagram, model chip only on model-authored runs, the consistency
// sweep (SYNTHETIC badge, gap count note, event ids behind a disclosure). Mock mode, desktop.

test.describe("lib/health: pass-rate text and chip provenance", () => {
  test("planLiveEvalText reads /health plan_live_eval", () => {
    expect(planLiveEvalText({ date: "2026-10-11", passed: 22, total: 24, p50_s: 26.5 })).toBe("Committed eval: 22/24 passed (11 Oct), p50 26.5 s");
    expect(planLiveEvalText({ date: "2026-10-11", passed: 24, total: 24 })).toBe("Committed eval: 24/24 passed (11 Oct)");
  });
  test("it is null when the field is absent or malformed", () => {
    expect(planLiveEvalText(undefined)).toBeNull();
    expect(planLiveEvalText(null)).toBeNull();
    expect(planLiveEvalText({ passed: 3 } as never)).toBeNull();
    expect(planLiveEvalText({ passed: 5, total: 4, p50_s: 1, date: "2026-10-11" })).toBeNull();
    expect(planLiveEvalText({ passed: 0, total: 0, p50_s: 1, date: "2026-10-11" })).toBeNull();
  });
  test("a top-level model wins over the vertex detail; without one the detail is read as before", () => {
    const detail = "credentials + project resolved (project=p, model=gemini-3.5-flash, fallback=x)";
    const h = (extra: object) => ({ checks: { vertex: { ok: true, checked_at: "x", detail } }, ...extra }) as never;
    expect(modelInfoFromHealth(h({ model: "gemini-9-pro" }))?.model).toBe("gemini-9-pro");
    expect(modelInfoFromHealth(h({}))?.model).toBe("gemini-3.5-flash");
    expect(modelInfoFromHealth({ checks: {}, model: "gemini-9-pro", backend: "vertex" } as never)).toEqual({ model: "gemini-9-pro", fallback: null, live: true });
    expect(modelInfoFromHealth(h({ model: "not a model id!" }))?.model).toBe("gemini-3.5-flash");
  });
  test("the chip names the model that authored the run; /health only when the run names none", () => {
    const today = { model: "gemini-9-pro", fallback: null, live: true };
    // a recording keeps its own model when today's configuration differs
    expect(chipModel("gemini-3.5-flash", today)).toEqual({ model: "gemini-3.5-flash", fallback: null, live: true });
    expect(chipModel(" gemini-3.5-flash ", null)?.model).toBe("gemini-3.5-flash");
    // no model on the run (an in-flight run, an older summary): today's configuration
    expect(chipModel(null, today)).toEqual(today);
    expect(chipModel(undefined, today)).toEqual(today);
    expect(chipModel("", today)).toEqual(today);
    expect(chipModel(null, null)).toBeNull();
    // a run that names a non-Gemini model (the scripted planner) never borrows today's model
    expect(chipModel("stub-planner", today)).toBeNull();
  });
  test("only recorded and live Gemini runs carry the model chip", () => {
    expect(showsModelChip("recorded_gemini")).toBe(true);
    expect(showsModelChip("live_gemini")).toBe(true);
    expect(showsModelChip("scripted_stub")).toBe(false);
    expect(showsModelChip("deterministic_rules")).toBe(false);
    expect(showsModelChip(null)).toBe(false);
    expect(showsModelChip(undefined)).toBe(false);
  });
});

test.describe("Desk: pass-rate chip and model chip honesty", () => {
  test("the Plan live panel shows the pass-rate chip", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await expect(page.getByTestId("plan-eval-chip")).toHaveText("Committed eval: 22/24 passed (11 Oct), p50 26.5 s");
  });
  test("it is absent, and nothing else changes, when /health fails or lacks the field", async ({ page }) => {
    await injectMockFaults(page, { "/health": { kind: "http" } });
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await expect(page.getByTestId("plan-live")).toBeVisible();
    await expect(page.getByTestId("plan-eval-chip")).toHaveCount(0);
  });
  test("a recorded Gemini trace shows the model chip next to its badge", async ({ page }) => {
    // Mock mode serves the one recorded trace for every play; the scripted-fixture case runs against
    // the stub backend in tests/live/desk_sources.spec.ts.
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const chips = page.getByTestId("play-detail").locator(".trace-panel").first();
    await expect(chips.getByText("Recorded from Gemini")).toBeVisible();
    await expect(chips.getByTestId("model-chip")).toBeVisible();
  });
  test("trace rows keep event ids out of sight until the technical details are opened", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const trace = page.getByTestId("play-detail").locator(".trace-panel").first();
    const first = trace.locator(".trace-panel__event").filter({ has: page.getByText("technical details") }).first();
    await expect(first.getByTestId("trace-event-id")).toBeHidden();
    await first.locator("summary", { hasText: "technical details" }).click();
    await expect(first.getByTestId("trace-event-id")).toContainText(/^Event /);
  });
  test("trace panel and Plan live panel show no raw ids outside the technical details", async ({ page }) => {
    const raw = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\brun_[a-z0-9_]*[0-9a-f]{8}\b|\b(?:refc|inv|evt)_[a-z0-9_]+/i;
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    const recorded = await card.locator(".trace-panel").first().innerText();
    expect(recorded).not.toMatch(raw);
    await card.getByTestId("plan-live").click();
    await expect(card.getByTestId("live-replan")).toBeVisible();
    expect(await card.getByTestId("live-replan").innerText()).not.toMatch(raw);
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    expect(await card.getByTestId("live-trace").innerText()).not.toMatch(raw);
    expect(await card.getByRole("heading", { name: "Re-plan result" }).locator("xpath=..").innerText()).not.toMatch(raw);
  });
  test("the re-plan result counts the attempts the trace shows and drops no chip it had", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("plan-live").click();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    const attemptsShown = await card.getByTestId("live-trace").locator('[data-testid^="trace-attempt-"]').count();
    const effort = card.getByTestId("rerun-effort");
    if (attemptsShown > 0) await expect(effort).toHaveText(new RegExp(`^\\s*${attemptsShown} attempts?$`));
    else await expect(effort).toContainText(/iteration/);
    // and it equals the trace's own summary line: "Guardrail attempts · N proposed[, M rejected]"
    const head = await card.getByTestId("live-trace").getByTestId("trace-attempts").locator("h5, h4, h3, p, summary").first().innerText();
    const proposed = Number(head.match(/(\d+) proposed/)?.[1]);
    expect(proposed).toBe(attemptsShown);
    await expect(effort).toHaveText(new RegExp(`^\\s*${proposed} attempts?$`));
  });
});

test.describe("landing: loop diagram", () => {
  test("the hero shows the loop diagram with alt text, and public/loop.svg is docs/loop.svg", async ({ page }) => {
    await page.goto("/");
    const img = page.getByTestId("loop-diagram");
    await expect(img).toBeVisible();
    await expect(img).toHaveAttribute("alt", /Forecast, Propose, Approve, Offer, Measure/);
    expect(await img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    const root = path.resolve(__dirname, "../../..");
    expect(fs.readFileSync(path.join(root, "web/public/loop.svg"), "utf-8")).toBe(fs.readFileSync(path.join(root, "docs/loop.svg"), "utf-8"));
  });
});

test.describe("Outcomes: consistency", () => {
  test("the header badge says SYNTHETIC, not LIVE, over the seeded data", async ({ page }) => {
    await page.goto("/outcomes");
    const h = page.locator(".card__header", { has: page.getByRole("heading", { name: "Outcomes", level: 1 }) });
    await expect(h.locator(".badge")).toContainText("SYNTHETIC");
    await expect(h.locator(".badge")).not.toContainText(/LIVE|REPLAY/);
  });
  test("the portfolio scan counts the same 550 gaps as the Desk, with nothing left to explain", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByTestId("portfolio-gap-count")).toHaveText("across 550 gaps");
    const card = page.getByTestId("portfolio-card");
    await expect(card).not.toContainText(/assortment/i);
    // the by-type rows add up to the headline count
    const counts = await card.locator(".portfolio-card__table tbody tr td:nth-child(2)").allInnerTexts();
    expect(counts.reduce((n, c) => n + Number(c.replace(/,/g, "")), 0)).toBe(550);
    await expect(card.locator(".portfolio-card__governor-line")).toContainText("126 of 550 gaps");
  });
});
