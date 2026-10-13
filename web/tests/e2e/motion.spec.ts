import { test, expect } from "@playwright/test";

// Motion (globals.css, "motion" block at the end): everything inside prefers-reduced-motion:
// no-preference; under reduce every element is in its final state at once.

test.describe("motion, no preference", () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
  });

  test("the first six blocks of a page rise in with a 40 ms stagger, and no more than six", async ({ page }) => {
    await page.goto("/outcomes");
    // read the declared animation, not the live one: under load it may already have finished
    const info = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main.page > *")).map((el) => {
        const cs = getComputedStyle(el);
        return cs.animationName === "rise" ? { duration: parseFloat(cs.animationDuration) * 1000, delay: parseFloat(cs.animationDelay) * 1000 } : null;
      }),
    );
    const animated = info.filter(Boolean);
    expect(animated.length).toBeGreaterThan(0);
    expect(animated.length).toBeLessThanOrEqual(6);
    for (const [i, a] of info.slice(0, 6).entries()) if (a) expect(a, `child ${i + 1}`).toEqual({ duration: 240, delay: i * 40 });
  });

  test("the rise leaves nothing behind: after it ends no transform or stacking context stays on the blocks", async ({ page }) => {
    await page.goto("/outcomes");
    await page.waitForTimeout(700);
    // a slow runner may still be playing a rise: wait for the animations themselves, not a longer timer
    await page.waitForFunction(() => document.getAnimations().every((a) => (a as CSSAnimation).animationName !== "rise"));
    const left = await page.evaluate(() => Array.from(document.querySelectorAll("main.page > *")).filter((el) => getComputedStyle(el).transform !== "none").length);
    expect(left).toBe(0);
  });

  test("the LIVE dot pulses over 2 s", async ({ page }) => {
    await page.goto("/");
    const d = await page.locator(".badge--live").first().evaluate((el) => {
      const a = document.getAnimations().find((x) => (x as CSSAnimation).animationName === "livePulse" && (x.effect as KeyframeEffect).target === el);
      return a ? a.effect?.getComputedTiming().duration : null;
    });
    expect(d).toBe(2000);
  });

  test("the decision card's projected figure counts up once over 600 ms, with the final value in the DOM text from the start", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => {
      const w = window as unknown as { __seen: string[]; __ghost: boolean };
      w.__seen = [];
      w.__ghost = false;
      new MutationObserver(() => {
        const el = document.querySelector('[data-testid="preview-figure-amount"]');
        if (el) w.__seen.push(el.textContent ?? "");
        if (document.querySelector('[data-testid="preview-figure-count"]')) w.__ghost = true;
      }).observe(document, { childList: true, subtree: true, characterData: true });
    });
    await page.goto("/");
    const amount = page.getByTestId("preview-figure-amount");
    await expect(amount).toHaveText("₹9,191");
    await expect.poll(() => page.evaluate(() => (window as unknown as { __ghost: boolean }).__ghost)).toBe(true);
    const seen = await page.evaluate(() => (window as unknown as { __seen: string[] }).__seen);
    expect(new Set(seen)).toEqual(new Set(["₹9,191"])); // the real text never showed another value
    await expect(page.getByTestId("preview-figure-count")).toHaveCount(0, { timeout: 3000 }); // and the count ends
    await expect(amount).toHaveText("₹9,191");
  });

  test("hover is colour and border only: no lift, no scale", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const cta = page.getByRole("button", { name: "Run the 60-second beat" });
    await cta.hover();
    await page.waitForTimeout(200);
    const s = await cta.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { transform: cs.transform, props: cs.transitionProperty, dur: cs.transitionDuration, shadow: cs.boxShadow };
    });
    expect(s.transform).toBe("none");
    expect(s.shadow).toBe("none");
    expect(s.props).not.toMatch(/transform|box-shadow|all/);
    expect(parseFloat(s.dur)).toBeGreaterThanOrEqual(0.11);
    expect(parseFloat(s.dur)).toBeLessThanOrEqual(0.15);
  });
});

test.describe("motion, reduced", () => {
  test("nothing rises, nothing pulses, and the figure shows its final value with no count-up copy", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("preview-figure-amount")).toHaveText("₹9,191");
    await expect(page.getByTestId("preview-figure-count")).toHaveCount(0);
    const running = await page.evaluate(() =>
      document.getAnimations().filter((a) => {
        const n = (a as CSSAnimation).animationName;
        return (n === "rise" || n === "livePulse") && a.playState === "running";
      }).length,
    );
    expect(running).toBe(0);
  });
});
