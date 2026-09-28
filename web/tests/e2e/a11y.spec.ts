import fs from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import type { AxeResults } from "axe-core";

// Every route, scanned with real axe-core (not a manual guess), at both desktop and a real phone
// viewport width -- per the WCAG-violations fix in b0565d1, re-run whenever the UI changes rather
// than assumed to still hold. Mock mode gives every route real, stable content without needing a
// running API.
const ROUTES = ["/", "/desk", "/phone", "/chat", "/stylist", "/trends", "/outcomes", "/feedback", "/feedback/results"];

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
