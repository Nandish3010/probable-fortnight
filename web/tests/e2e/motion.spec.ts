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

  test("the decision card's projected figure never counts: the final value is the text from the first frame, brought in by a short fade", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => {
      const w = window as unknown as { __seen: { t: number; text: string }[]; __overlay: boolean };
      w.__seen = [];
      w.__overlay = false;
      const note = () => {
        const el = document.querySelector('[data-testid="preview-figure-amount"]');
        if (el) w.__seen.push({ t: performance.now(), text: el.textContent ?? "" });
        if (document.querySelector('[data-testid="preview-figure-count"]')) w.__overlay = true;
      };
      new MutationObserver(note).observe(document, { childList: true, subtree: true, characterData: true });
      const loop = () => {
        note();
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    });
    await page.goto("/");
    const amount = page.getByTestId("preview-figure-amount");
    await expect(amount).toHaveText("₹9,191");
    // let the first 400 ms after it appeared go by, then read everything that was ever on screen
    await page.waitForTimeout(500);
    const { seen, overlay } = await page.evaluate(() => {
      const w = window as unknown as { __seen: { t: number; text: string }[]; __overlay: boolean };
      return { seen: w.__seen, overlay: w.__overlay };
    });
    expect(overlay).toBe(false); // no aria-hidden counting copy any more
    expect(seen.length).toBeGreaterThan(5);
    expect(new Set(seen.map((s) => s.text))).toEqual(new Set(["₹9,191"])); // never another value, from the first sighting on
    // the figure is final at about 0, 100 and 300 ms after it first appeared
    const t0 = seen[0].t;
    for (const at of [0, 100, 300]) {
      const near = seen.find((s) => s.t - t0 >= at);
      expect(near?.text, `at ~${at} ms`).toBe("₹9,191");
    }
    await expect(page.getByTestId("preview-figure-count")).toHaveCount(0);
  });

  test("the figure's fade is opacity only and no longer than 200 ms", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.addInitScript(() => {
      const w = window as unknown as { __fade: { duration: number; props: string[] } | null };
      w.__fade = null;
      const loop = () => {
        for (const a of document.getAnimations()) {
          if (/figureFade/.test((a as CSSAnimation).animationName ?? "") && !w.__fade) {
            const e = a.effect as KeyframeEffect;
            w.__fade = { duration: Number(e.getComputedTiming().duration), props: Array.from(new Set(e.getKeyframes().flatMap((k) => Object.keys(k)))) };
          }
        }
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    });
    await page.goto("/");
    await expect(page.getByTestId("preview-figure-amount")).toHaveText("₹9,191");
    const fade = await page.evaluate(() => (window as unknown as { __fade: { duration: number; props: string[] } | null }).__fade);
    expect(fade).not.toBeNull();
    expect(fade!.duration).toBeLessThanOrEqual(200);
    expect(fade!.props.filter((p) => !["offset", "easing", "composite", "computedOffset"].includes(p))).toEqual(["opacity"]);
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
  test("nothing rises, nothing pulses, and the figure shows its final value with no fade and no counting copy", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("preview-figure-amount")).toHaveText("₹9,191");
    await expect(page.getByTestId("preview-figure-count")).toHaveCount(0);
    const running = await page.evaluate(() =>
      document.getAnimations().filter((a) => {
        const n = (a as CSSAnimation).animationName;
        return (n === "rise" || n === "livePulse" || /figureFade/.test(n)) && a.playState === "running";
      }).length,
    );
    expect(running).toBe(0);
  });
});
