import { test, expect } from "@playwright/test";
import { approveSettled, assertNoHorizontalOverflow, openBeat } from "./helpers";

// The approved forecast chart's lift legend ("Extra units sold because of the play") used to sit
// on the right edge of the offer window, over the end of the line. It now lives in the band above
// the plot. This asserts it from geometry, not from a screenshot: no sampled point of any series
// path lies in the legend's box, the legend ends above the plot, and the page does not scroll
// sideways. Mock mode, both widths, both colour schemes.

for (const scheme of ["light", "dark"] as const) {
  for (const width of [1280, 375, 360]) {
    test(`the lift legend is clear of the lines and the plot at ${width} px wide, ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width, height: 900 });
      await openBeat(page);
      await page.getByTestId("approve-button").first().click();
      await approveSettled(page);
      await page.waitForTimeout(300);

      const r = await page.evaluate(() => {
        const svg = document.querySelector("svg.forecast-chart") as SVGSVGElement;
        const key = svg.querySelector('[data-testid="chart-lift-key"]') as SVGGElement | null;
        if (!key) return null;
        const kb = key.getBBox();
        const win = svg.querySelector('[data-testid="chart-window"]') as SVGRectElement;
        const plotTop = win.y.baseVal.value;
        const vb = svg.viewBox.baseVal;
        const pad = 3;
        const hits: string[] = [];
        let samples = 0;
        svg.querySelectorAll("path").forEach((p, pi) => {
          const len = p.getTotalLength();
          for (let d = 0; d <= len; d += 1) {
            const pt = p.getPointAtLength(d);
            samples += 1;
            if (pt.x >= kb.x - pad && pt.x <= kb.x + kb.width + pad && pt.y >= kb.y - pad && pt.y <= kb.y + kb.height + pad) {
              hits.push(`path ${pi} at ${pt.x.toFixed(0)},${pt.y.toFixed(0)}`);
              break;
            }
          }
        });
        // every gridline and the axis starts at or below the plot top, so the legend box must end above it
        const lines = Array.from(svg.querySelectorAll("line")).map((l) => (l as SVGLineElement).y1.baseVal.value);
        const texts = Array.from(key.querySelectorAll("text")).map((t) => t.textContent);
        return { kb: { x: kb.x, y: kb.y, r: kb.x + kb.width, b: kb.y + kb.height }, plotTop, vbW: vb.width, hits, samples, minLineY: Math.min(...lines), texts };
      });
      expect(r, "the legend is drawn").not.toBeNull();
      expect(r!.samples).toBeGreaterThan(100);
      expect(r!.hits, `series paths inside the legend box: ${r!.hits.join("; ")}`).toEqual([]);
      expect(r!.kb.b, "the legend ends above the plot").toBeLessThanOrEqual(r!.plotTop);
      expect(r!.kb.b).toBeLessThanOrEqual(r!.minLineY);
      expect(r!.kb.x).toBeGreaterThanOrEqual(0);
      expect(r!.kb.r).toBeLessThanOrEqual(r!.vbW);
      expect(r!.texts).toEqual(["Extra units sold", "because of the play"]);
      await assertNoHorizontalOverflow(page);
    });
  }
}
