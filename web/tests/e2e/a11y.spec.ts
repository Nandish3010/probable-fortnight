import fs from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import type { AxeResults } from "axe-core";
import { openBeat } from "./helpers";

// Every route, scanned with real axe-core (not a manual guess), at both desktop and a real phone
// viewport width -- per the WCAG-violations fix in b0565d1, re-run whenever the UI changes rather
// than assumed to still hold. Mock mode gives every route real, stable content without needing a
// running API.
const ROUTES = ["/", "/desk", "/phone", "/chat", "/outcomes", "/feedback", "/feedback/results"];

// Opt-in evidence capture: unset in routine runs (dev machines, CI), so `make web-test` never
// dirties a committed directory. Set to write one JSON file per route+viewport here, e.g.
//   TAAL_A11Y_REPORT_DIR=../eval/raw/a11y_2026-09-28 npm test -- tests/e2e/a11y.spec.ts
// (see that directory's README.md for the exact command used to produce the committed report).
const REPORT_DIR = process.env.TAAL_A11Y_REPORT_DIR;

function writeReport(route: string, viewport: "desktop" | "phone", results: AxeResults) {
  if (!REPORT_DIR) return;
  fs.mkdirSync(REPORT_DIR, { recursive: true });
  const slug = route === "/" ? "root" : route.replace(/^\//, "").replace(/\//g, "_");
  const report = {
    route,
    viewport,
    scanned_at: new Date().toISOString(),
    axe_core_version: results.testEngine.version,
    tags: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
    violations: results.violations,
    passes_count: results.passes.length,
    incomplete_count: results.incomplete.length,
    inapplicable_count: results.inapplicable.length,
  };
  fs.writeFileSync(path.join(REPORT_DIR, `${viewport}__${slug}.json`), JSON.stringify(report, null, 2));
}

// Scan the settled page, not a frame of the fadeInUp entrance: mid-fade, text is blended toward the
// background and axe reads a lower contrast than the page actually has (a 0.61s animation vs the
// 300ms wait below raced on slower CI runners). globals.css already collapses every animation
// under prefers-reduced-motion, so emulating it gives the final colours immediately.
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

for (const route of ROUTES) {
  test(`axe: ${route} (desktop) has no violations`, async ({ page }) => {
    await page.goto(route);
    await page.waitForTimeout(300);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    writeReport(route, "desktop", results);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
}

test.describe("phone viewport (390x844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const route of ROUTES) {
    test(`axe: ${route} (phone) has no violations`, async ({ page }) => {
      await page.goto(route);
      await page.waitForTimeout(300);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      writeReport(route, "phone", results);
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  }
});

// States beyond the first paint: the decision card open, after Approve, the legend and Reset dialog
// open, in light and dark, desktop and phone. (Contrast is where a state usually fails.)
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 390, height: 844 }]] as const) {
    test.describe(`${scheme} ${name}: states`, () => {
      test.use({ viewport, colorScheme: scheme });

      test("landing: beat open (on a phone, the feed), Details and legend open", async ({ page }) => {
        await page.goto("/");
        await page.getByTestId("state-legend").locator("summary").click();
        const card = await openBeat(page, { goto: false });
        await card.getByTestId("guardrail-summary").click();
        await card.getByTestId("card-details").locator("summary").click();
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });

      test("landing: after Approve", async ({ page }) => {
        const card = await openBeat(page);
        await card.getByRole("button", { name: "Approve" }).click();
        await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });

      test("landing: Reset dialog open", async ({ page }) => {
        await page.goto("/");
        await page.getByRole("button", { name: "Reset demo data" }).click();
        await page.getByRole("dialog").waitFor();
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });

      test("desk: a play open with Details open", async ({ page }) => {
        await page.goto("/desk");
        await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
        await page.getByTestId("card-details").locator("summary").click();
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });

      test("phone view: after capture and Approve", async ({ page }) => {
        await page.goto("/phone");
        await page.getByRole("button", { name: "Pallet 1" }).click();
        await page.getByTestId("intake-table").waitFor();
        await page.getByRole("button", { name: "Confirm rows" }).click();
        await page.getByTestId("why-now").waitFor();
        await page.getByRole("button", { name: "Approve" }).click();
        await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });
    });
  }
}
