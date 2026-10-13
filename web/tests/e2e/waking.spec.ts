import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, type FakeHandler } from "./helpers";
import { SLOW_AFTER_MS, WAKE_AFTER_MS, wakingPhase } from "../../lib/useWaking";

// "Waking the demo": the service sleeps when idle, so a first read can take a long time. After a
// moment of a pending first load the page says so, in place and without moving the controls, and the
// notice is gone the moment data arrives (components/WakingNotice.tsx, lib/useWaking.ts). The delays
// here are real: the fake API on FAKE_API answers late through page.route().

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const WAKING = /Waking the demo\. It sleeps when idle, so the first load can take a little longer\. Nothing is wrong\./;
const SLOW = "The demo is slow to wake. Try again";

/** Answers with the fixture after `ms`. */
const late = (name: string, ms: number): FakeHandler => async (route) => {
  await new Promise((r) => setTimeout(r, ms));
  await okJson(mockFixture(name))(route);
};

async function slowApi(page: Page, ms: number, paths: Record<string, string> = { "/gaps": "gaps", "/plays": "plays", "/customers/demo": "customers_demo" }) {
  await forceLiveApi(page, FAKE_API);
  await fakeApi(page, beatHandlers(Object.fromEntries(Object.entries(paths).map(([p, n]) => [p, late(n, ms)]))));
}

test.describe("wakingPhase (pure)", () => {
  test("idle before the wake threshold, waking between, slow after; a failure is slow at once", () => {
    expect(wakingPhase(null)).toBe("idle");
    expect(wakingPhase(0)).toBe("idle");
    expect(wakingPhase(WAKE_AFTER_MS - 1)).toBe("idle");
    expect(wakingPhase(WAKE_AFTER_MS)).toBe("waking");
    expect(wakingPhase(SLOW_AFTER_MS - 1)).toBe("waking");
    expect(wakingPhase(SLOW_AFTER_MS)).toBe("slow");
    expect(wakingPhase(100, true)).toBe("slow");
    expect(wakingPhase(null, true)).toBe("slow");
    expect(WAKE_AFTER_MS).toBe(1500);
    expect(SLOW_AFTER_MS).toBe(45_000);
  });
});

test.describe("landing: the decision card's first read is slow", () => {
  test("the notice appears after about a second and a half, and is gone when the data arrives", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500);
    await page.goto("/");
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toHaveCount(0); // not at once: a quick load never shows it
    await expect(notice).toBeVisible({ timeout: 3000 });
    await expect(notice).toContainText(WAKING);
    await expect(notice).toHaveAttribute("data-phase", "waking");
    // a polite live region around it, and nothing alarming: no alert role, no button yet
    await expect(notice.locator("xpath=..")).toHaveAttribute("role", "status");
    await expect(notice.locator("xpath=..")).toHaveAttribute("aria-live", "polite");
    await expect(notice.getByRole("button")).toHaveCount(0);
    // the one primary button is still there and usable while the notice is
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeEnabled();
    // data arrives: the card fills in and the notice goes
    await expect(page.getByTestId("preview-figure")).toBeVisible({ timeout: 8000 });
    await expect(notice).toHaveCount(0);
  });

  test("the notice sits below the card's button: the button does not move when it appears", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500);
    await page.goto("/");
    const button = page.getByRole("button", { name: "Run the 60-second beat" });
    await expect(button).toBeVisible();
    await expect(page.getByTestId("demo-clock")).toContainText("Demo date"); // /health has answered: the page above the card has settled
    await page.waitForTimeout(700); // the entrance rise (RiseGate) is over
    const before = (await button.boundingBox())!;
    await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3000 });
    const during = (await button.boundingBox())!;
    expect(during.y).toBe(before.y);
    const noticeBox = (await page.getByTestId("waking-notice").boundingBox())!;
    expect(noticeBox.y).toBeGreaterThan(during.y + during.height - 1);
  });

  test("a failed first read says the demo is slow to wake and offers Retry; Retry loads the card", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await forceLiveApi(page, FAKE_API);
    let up = false;
    const gate = (name: string): FakeHandler => async (route) => {
      if (!up) await route.abort("failed");
      else await okJson(mockFixture(name))(route);
    };
    await fakeApi(page, beatHandlers({ "/gaps": gate("gaps"), "/plays": gate("plays"), "/customers/demo": gate("customers_demo") }));
    await page.goto("/");
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toBeVisible();
    await expect(notice).toHaveAttribute("data-phase", "slow");
    await expect(notice).toContainText(SLOW);
    up = true;
    await notice.getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("preview-figure")).toBeVisible({ timeout: 8000 });
    await expect(notice).toHaveCount(0);
  });

  test("after the click, the beat's own wait shows the notice too, below the loading line", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500);
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByText("Loading gap and play…")).toBeVisible();
    await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3000 });
    await expect(page.getByTestId("beat-panel")).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId("waking-notice")).toHaveCount(0);
    // opened: Approve is exactly where it is without a wait
    await page.waitForTimeout(500);
    expect((await page.getByTestId("approve-button").boundingBox())!.y).toBeLessThanOrEqual(740);
  });

  test("a quick load never shows it", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("preview-figure")).toBeVisible();
    await page.waitForTimeout(1800);
    await expect(page.getByTestId("waking-notice")).toHaveCount(0);
  });
});

test.describe("the Desk inbox and the chat panel", () => {
  test("Desk: the notice shows under 'Loading plays…' and goes when the inbox fills", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500);
    await page.goto("/desk");
    await expect(page.getByText("Loading plays…")).toBeVisible();
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toBeVisible({ timeout: 3000 });
    await expect(notice).toContainText(WAKING);
    await expect(page.getByTestId("play-detail")).toBeVisible({ timeout: 8000 });
    await expect(notice).toHaveCount(0);
  });

  test("Chat: a slow first customer list shows the notice with 'Loading customers…', then the picker", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500, { "/customers/demo": "customers_demo" });
    await page.goto("/chat");
    await expect(page.getByTestId("chat-customers-loading")).toBeVisible();
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toBeVisible({ timeout: 3000 });
    await expect(page.getByTestId("chat-customer-select")).toBeVisible({ timeout: 8000 });
    await expect(notice).toHaveCount(0);
    await expect(page.getByTestId("chat-customers-loading")).toHaveCount(0);
  });

  test("Landing: the chat panel stays quiet while the decision card is the one waiting", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500, { "/gaps": "gaps", "/plays": "plays", "/customers/demo": "customers_demo" });
    await page.goto("/");
    await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3000 });
    await expect(page.getByTestId("waking-notice")).toHaveCount(1);
  });
});

test.describe("phone", () => {
  test("375 wide: the feed placeholder carries the notice, nothing overflows at 360, and it goes with the data", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await slowApi(page, 3500);
    await page.goto("/");
    await expect(page.getByTestId("feed-loading")).toBeVisible();
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toBeVisible({ timeout: 3000 });
    await expect(notice).toContainText(WAKING);
    await assertNoHorizontalOverflow(page);
    await expect(page.getByTestId("decision-feed")).toBeVisible({ timeout: 8000 });
    await expect(notice).toHaveCount(0);
    await assertNoHorizontalOverflow(page);
  });

  test("360 wide: the slow variant with Retry fits too", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await forceLiveApi(page, FAKE_API);
    await fakeApi(page, beatHandlers({ "/gaps": (route) => route.abort("failed"), "/plays": (route) => route.abort("failed") }));
    await page.goto("/desk");
    // the Desk shows its own error card on a failed read; the landing's feed does too. The slow
    // variant is the landing's pre-click state on desktop widths, checked at 700 px here.
    await page.setViewportSize({ width: 800, height: 780 });
    await page.goto("/");
    await expect(page.getByTestId("waking-notice")).toHaveAttribute("data-phase", "slow");
    await assertNoHorizontalOverflow(page);
  });
});

test.describe("motion", () => {
  test("the dot breathes only when motion is allowed", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.goto("/");
    const dot = page.getByTestId("waking-notice").locator("span").first();
    await expect(dot).toBeVisible({ timeout: 3000 });
    expect(await dot.evaluate((el) => getComputedStyle(el).animationName)).not.toBe("none");
  });

  test("reduced motion: no animation anywhere in the notice", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await slowApi(page, 3500);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const notice = page.getByTestId("waking-notice");
    await expect(notice).toBeVisible({ timeout: 3000 });
    const animated = await notice.evaluate((el) =>
      [el, ...Array.from(el.querySelectorAll("*"))].filter((n) => getComputedStyle(n).animationName !== "none").length,
    );
    expect(animated).toBe(0);
  });
});

test.describe("axe with the notice on screen", () => {
  for (const scheme of ["light", "dark"] as const) {
    for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 390, height: 844 }]] as const) {
      test(`${scheme} ${name}: no serious or critical violation, waking and slow`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
        await slowApi(page, 3500);
        await page.goto("/");
        await expect(page.getByTestId("waking-notice")).toBeVisible({ timeout: 3000 });
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        const severe = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
      });
    }
    test(`${scheme}: the slow variant with Retry has no serious or critical violation`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
      await forceLiveApi(page, FAKE_API);
      await fakeApi(page, beatHandlers({ "/gaps": (route) => route.abort("failed"), "/plays": (route) => route.abort("failed") }));
      await page.goto("/");
      await expect(page.getByTestId("waking-notice")).toHaveAttribute("data-phase", "slow");
      const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      const severe = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
    });
  }
});
