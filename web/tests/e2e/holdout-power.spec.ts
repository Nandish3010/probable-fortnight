import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { HOLDOUT_POWER, powerLineText } from "../../lib/holdoutPower";
import { assertNoHorizontalOverflow } from "./helpers";

// The Outcomes power line: every number comes from lib/holdoutPower.ts, and this spec reads the
// committed simulation file from disk so the constants cannot drift from it.

const FILE = path.resolve(__dirname, "../../..", HOLDOUT_POWER.source); // from web/: ../eval/raw/holdout_power_2026-10-14.json
const power = JSON.parse(fs.readFileSync(FILE, "utf-8"));
const tea = power.outputs.tea_organic;

test.describe("lib/holdoutPower: the constants equal the committed file", () => {
  test("the file is the simulation, the Tea case is primary, and the web constants equal it", () => {
    expect(power.label).toBe("SIMULATION of the measurement design, not a result");
    expect(tea.primary).toBe(true);
    expect(HOLDOUT_POWER.source).toBe("eval/raw/holdout_power_2026-10-14.json");
    expect(HOLDOUT_POWER.treated).toBe(power.inputs.design.treated);
    expect(HOLDOUT_POWER.heldOut).toBe(power.inputs.design.held_out);
    expect(power.inputs.design.split).toBe("90/10");
    expect(HOLDOUT_POWER.powerPct).toBe(Math.round(power.inputs.power * 100));
    expect(HOLDOUT_POWER.confidencePct).toBe(Math.round(power.inputs.confidence * 100));
    expect(HOLDOUT_POWER.minDetectableLiftPp).toBe(tea.min_detectable_lift_pp_at_355_39);
    expect(power.inputs.lifts_pp).toContain(HOLDOUT_POWER.resolveLiftPp);
    expect(HOLDOUT_POWER.resolveTotalN).toBe(tea.total_n_for_lift_at_90_10_split[`${HOLDOUT_POWER.resolveLiftPp}pp`].total_n);
  });

  test("the sentence is the agreed one, numbers formatted for reading", () => {
    expect(powerLineText()).toBe(
      "The Tea beat's holdout (355 treated, 39 held out) is under-powered by design. At the seeded base rate it could only detect a lift of about 12.4 pp (80% power, 95% confidence); resolving a 5 pp lift would take about 1,156 orders at the same 90/10 split. A simulation of the measurement design, not a result.",
    );
  });

  test("each figure in the sentence is one of the file's", () => {
    const text = powerLineText();
    const fromFile = [
      power.inputs.design.treated,
      power.inputs.design.held_out,
      tea.min_detectable_lift_pp_at_355_39.toFixed(1),
      Math.round(power.inputs.power * 100),
      Math.round(power.inputs.confidence * 100),
      5,
      tea.total_n_for_lift_at_90_10_split["5pp"].total_n.toLocaleString("en-US"),
    ].map(String);
    const numbers = (text.match(/\d[\d,]*(?:\.\d+)?/g) ?? []).filter((n) => n !== "90" && n !== "10"); // the 90/10 split is named in the file
    expect(numbers.sort()).toEqual([...fromFile].sort());
  });
});

async function seedApprovedChips(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("taal_visitor", "v-power");
    window.localStorage.setItem(
      "taal_progress:v-power",
      JSON.stringify({
        spot: true,
        plan: true,
        offer: true,
        approved: [{ play_id: "play_chips_ds07_v1", gap_id: "gap_chips_ds07", at: "2026-09-12T03:30:00Z" }],
      }),
    );
    window.localStorage.setItem("taal_mock_approved", JSON.stringify(["play_chips_ds07_v1"]));
  });
}

test.describe("outcomes: the power line", () => {
  test("it shows with the pre-measure card, under the result card, tagged SIMULATION", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByTestId("summary-empty")).toBeVisible();
    const line = page.getByTestId("power-line");
    await expect(line).toBeVisible();
    await expect(line).toHaveText(`SIMULATION${powerLineText()}`);
    await expect(line.locator(".basis")).toHaveText("SIMULATION");
    const order = await page.locator("main > section, main > p[data-testid], main > .card").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.testid ?? ""));
    expect(order.indexOf("power-line")).toBe(order.indexOf("outcome-summary") + 1);
  });

  test("it shows with the measured result card, outside the Inconclusive badge, and claims no measured lift", async ({ page }) => {
    await seedApprovedChips(page);
    await page.goto("/outcomes");
    await expect(page.getByTestId("outcome-summary").getByTestId("inconclusive-badge")).toBeVisible();
    const line = page.getByTestId("power-line");
    await expect(line).toBeVisible();
    await expect(line).toContainText("under-powered by design");
    await expect(line).toContainText("A simulation of the measurement design, not a result.");
    await expect(page.getByTestId("inconclusive-badge").locator("[data-testid='power-line']")).toHaveCount(0);
    expect(await line.evaluate((el) => el.closest("[data-testid='inconclusive-badge']"))).toBeNull();
    expect(await line.evaluate((el) => el.closest("[data-testid='outcome-summary']"))).toBeNull();
    const text = (await line.innerText()).toLowerCase();
    for (const bad of ["measured lift", "we measured", "proved", "profit", "pilot"]) expect(text).not.toContain(bad);
  });

  test("the tag is 14 px or more at weight 600 and the note stays out of the data-basis rupee rule", async ({ page }) => {
    await page.goto("/outcomes");
    const tag = page.getByTestId("power-line").locator(".basis");
    const style = await tag.evaluate((el) => {
      const s = getComputedStyle(el);
      return { size: parseFloat(s.fontSize), weight: Number(s.fontWeight) };
    });
    expect(style.size).toBeGreaterThanOrEqual(14);
    expect(style.weight).toBeGreaterThanOrEqual(600);
    expect(await page.getByTestId("power-line").innerText()).not.toContain("₹");
  });

  for (const width of [375, 360]) {
    test(`no sideways overflow at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 812 });
      await seedApprovedChips(page);
      await page.goto("/outcomes");
      await expect(page.getByTestId("power-line")).toBeVisible();
      await assertNoHorizontalOverflow(page);
      const box = (await page.getByTestId("power-line").boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(width);
    });
  }
});

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 375, height: 812 }]] as const) {
    test.describe(`outcomes power line: axe (${scheme}, ${name})`, () => {
      test.use({ viewport, colorScheme: scheme });
      for (const seeded of [false, true]) {
        test(`${seeded ? "measured" : "pre-measure"} has no violations`, async ({ page }) => {
          await page.emulateMedia({ reducedMotion: "reduce" });
          if (seeded) await seedApprovedChips(page);
          await page.goto("/outcomes");
          await expect(page.getByTestId("power-line")).toBeVisible();
          await page.waitForTimeout(300);
          const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
          expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
        });
      }
    });
  }
}
