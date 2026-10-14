import fs from "node:fs";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";

// Plan row 4.1: axe on the five routes, light and dark, desktop and phone, with serious and critical
// counts per cell. Every cell must be zero. Set TAAL_AXE_REPORT=1 to write the table to
// tests/axe_report_<date>.md (run once on a single worker so the rows come out in order):
//   TAAL_AXE_REPORT=1 npm test -- tests/e2e/axe-report.spec.ts --project=desktop --workers=1
const ROUTES = ["/", "/desk", "/phone", "/chat", "/outcomes"];
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"];
const VIEWPORTS = { desktop: { width: 1280, height: 800 }, phone: { width: 390, height: 844 } } as const;
const REPORT = process.env.TAAL_AXE_REPORT ? path.resolve(__dirname, "..", "axe_report_2026-10-14.md") : null;
const rows: string[] = [];
const findings: string[] = [];

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  if (REPORT) {
    rows.length = 0;
    findings.length = 0;
  }
});

test.afterAll(() => {
  if (!REPORT || rows.length === 0) return;
  const head = [
    "# Axe report, 14 Oct 2026 (final-week B4; supersedes the 12 Oct report, which is kept)",
    "",
    "Mock mode, `@axe-core/playwright`, tags wcag2a, wcag2aa, wcag21a, wcag21aa and best-practice (the 12 Oct report left best-practice out, which is why it showed no moderate findings), reduced motion on, page settled 300 ms after load.",
    "Produced by `tests/e2e/axe-report.spec.ts` (`TAAL_AXE_REPORT=1`). Desktop is 1280x800, phone is 390x844.",
    "A cell is the number of violations axe rates serious or critical; the last column counts the moderate and minor ones. First paint of each route only; the open-card, post-Approve and dialog states are in a11y.spec.ts and demo-path.spec.ts.",
    "",
    "| Route | Theme | Viewport | Serious + critical | Moderate + minor |",
    "|---|---|---|---|---|",
  ];
  const total = rows.length;
  const bad = rows.filter((r) => !/\| 0 \| \d+ \|$/.test(r)).length;
  const tail = [
    "",
    `${total} scans; ${bad} with a serious or critical violation.`,
    "",
    "## Moderate and minor findings (rule ids)",
    "",
    ...(findings.length ? findings : ["None."]),
    "",
  ];
  fs.writeFileSync(REPORT, [...head, ...rows, ...tail].join("\n"));
});

for (const scheme of ["light", "dark"] as const) {
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`${scheme} ${vpName}`, () => {
      test.use({ viewport, colorScheme: scheme });
      for (const route of ROUTES) {
        test(`${route}`, async ({ page }) => {
          await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
          await page.goto(route);
          await page.waitForTimeout(300);
          const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
          const severe = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
          const mild = results.violations.length - severe.length;
          rows.push(`| ${route} | ${scheme} | ${vpName} | ${severe.length} | ${mild} |`);
          for (const v of results.violations.filter((x) => x.impact !== "serious" && x.impact !== "critical")) {
            findings.push(`- ${route}, ${scheme}, ${vpName}: \`${v.id}\` (${v.impact}, ${v.nodes.length} node${v.nodes.length === 1 ? "" : "s"})`);
          }
          expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
        });
      }
    });
  }
}
