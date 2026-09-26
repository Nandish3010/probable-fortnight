import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";

// Every route, scanned with real axe-core (not a manual guess), at both desktop and a real phone
// viewport width -- per the WCAG-violations fix in b0565d1, re-run whenever the UI changes rather
// than assumed to still hold. Mock mode gives every route real, stable content without needing a
// running API.
const ROUTES = ["/", "/desk", "/phone", "/chat", "/stylist", "/trends", "/outcomes"];

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
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  }
});
