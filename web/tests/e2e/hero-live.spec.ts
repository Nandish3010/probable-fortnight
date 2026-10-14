import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockCalls, mockFixture, okJson, settledRects } from "./helpers";

// The landing's second way in: "Watch Gemini plan a play live" (a quiet link beside the one primary
// button, with the committed pass-rate chip), which opens the Desk on the flagship gap and starts
// Plan live there once; and, on a phone, a compact DOM loop in the stepper's own words where
// public/loop.svg is hidden.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const GEMINI_LABEL = "Watch Gemini plan a play live";
const SCRIPTED_LABEL = "Watch the scripted planner run live";
const EVAL_TEXT = "22/24 live plans passed on gemini-3.5-flash (11 Oct), p50 26.5 s · committed eval";

/** Runs the landing against a fake API whose /health names the given backend. */
async function withBackend(page: import("@playwright/test").Page, backend: "vertex" | "stub") {
  await forceLiveApi(page, FAKE_API);
  await fakeApi(page, beatHandlers({ "/health": okJson({ ...mockFixture("health"), backend }) }));
}

test.describe("the secondary action on the landing (1280 x 800)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("on a service that runs Gemini the link reads 'Watch Gemini plan a play live', beside the primary button", async ({ page }) => {
    await withBackend(page, "vertex");
    await page.goto("/");
    const link = page.getByTestId("watch-plan-live");
    await expect(link).toHaveText(GEMINI_LABEL);
    await expect(page.getByRole("link", { name: GEMINI_LABEL })).toHaveAttribute("href", "/desk?plan=live");
    const cta = page.getByRole("button", { name: "Run the 60-second beat" });
    const [a, b] = await settledRects(cta, link);
    expect(Math.abs(a.y + a.height / 2 - (b.y + b.height / 2))).toBeLessThan(a.height); // the same row
    expect(b.x).toBeGreaterThan(a.x + a.width - 1);
    expect(b.height).toBeGreaterThanOrEqual(44);
  });

  test("it is a quiet text link: exactly one filled button on the landing, and the link has no fill or border", async ({ page }) => {
    await withBackend(page, "vertex");
    await page.goto("/");
    const link = page.getByTestId("watch-plan-live");
    await expect(link).toBeVisible();
    await expect(page.locator(".hero__cta")).toHaveCount(1);
    const css = await link.evaluate((el) => {
      const s = getComputedStyle(el);
      return { bg: s.backgroundColor, border: s.borderTopWidth, deco: s.textDecorationLine };
    });
    expect(css.bg).toBe("rgba(0, 0, 0, 0)");
    expect(css.border).toBe("0px");
    expect(css.deco).toBe("underline");
  });

  test("the pass-rate chip sits beside it, reads /health plan_live_eval, and does not call a committed eval live", async ({ page }) => {
    await withBackend(page, "vertex");
    await page.goto("/");
    const chip = page.getByTestId("plan-eval-chip");
    await expect(chip).toHaveText(EVAL_TEXT);
    await expect(chip).toContainText("committed eval"); // a dated record, never presented as a live reading
    await expect(chip).not.toContainText(/live reading|live now|LIVE ·/i);
    await expect(chip).toHaveAttribute("title", /24 live planner runs on 2026-10-11/);
    const [l, c] = await settledRects(page.getByTestId("watch-plan-live"), chip);
    expect(c.y).toBeGreaterThanOrEqual(l.y + l.height - 1); // under the link, in its column
    expect(c.y - (l.y + l.height)).toBeLessThan(12);
    expect(Math.abs(c.x - l.x)).toBeLessThan(12);
  });

  test("no chip when /health carries no plan_live_eval; the link still shows", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const { plan_live_eval: _gone, ...health } = mockFixture("health");
    void _gone;
    await fakeApi(page, beatHandlers({ "/health": okJson({ ...health, backend: "vertex" }) }));
    await page.goto("/");
    await expect(page.getByTestId("watch-plan-live")).toBeVisible();
    await expect(page.getByTestId("plan-eval-chip")).toHaveCount(0);
  });

  test("on the scripted backend the link says so: no 'Gemini' on a scripted fixture", async ({ page }) => {
    await withBackend(page, "stub");
    await page.goto("/");
    const link = page.getByTestId("watch-plan-live");
    await expect(link).toHaveText(SCRIPTED_LABEL);
    await expect(link).not.toContainText("Gemini");
    await expect(link).toHaveAttribute("title", /no model call/);
  });

  test("it is not shown before /health has answered, and not at all when /health fails", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(page, beatHandlers({ "/health": (route) => route.abort("failed") }));
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeVisible();
    await page.waitForTimeout(600);
    await expect(page.getByTestId("watch-plan-live")).toHaveCount(0);
  });

  test("once the beat is open the link is gone and Approve is where it was (<= 740)", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("watch-plan-live")).toBeVisible();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("watch-plan-live")).toHaveCount(0);
    await page.waitForTimeout(600);
    const box = (await page.getByTestId("approve-button").boundingBox())!;
    expect(box.y).toBeLessThanOrEqual(740);
  });
});

test.describe("the link starts Plan live on the Desk, once", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("click: the Desk opens on the flagship play and the planning steps stream; one run was requested", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("watch-plan-live").click();
    await expect(page).toHaveURL(/\/desk$/); // the one-shot parameter is removed from the address
    const detail = page.getByTestId("play-detail");
    await expect(detail).toContainText("Tea"); // the flagship gap, not the first row of some other order
    await expect(detail.getByTestId("plan-live")).toHaveText("Planning live…");
    const progress = detail.getByTestId("plan-progress");
    await expect(progress).toBeVisible();
    await expect(progress.getByTestId("plan-step")).toHaveCount(4);
    await expect(progress.getByTestId("plan-step").first()).toContainText("Reading the forecast");
    // provenance labels stream with it; the mock service is the scripted backend, so no Gemini anywhere
    await expect(progress.getByTestId("plan-step").nth(1).getByTestId("plan-step-provenance")).toHaveText("scripted fixture, no model call");
    await expect(progress.getByText(/Gemini/)).toHaveCount(0);
    await expect(progress.locator('[data-testid="plan-step"][data-state="done"]').first()).toBeVisible();
    await expect(page.getByTestId("rerun-effort")).toBeVisible({ timeout: 30_000 }); // the run finishes
    expect(await mockCalls(page, "/rerun")).toBe(1);
  });

  test("opening /desk?plan=live directly starts exactly one run, and a reload of the clean address starts none", async ({ page }) => {
    await page.goto("/desk?plan=live");
    await expect(page.getByTestId("plan-live")).toHaveText("Planning live…");
    await expect(page).toHaveURL(/\/desk$/);
    await expect.poll(() => mockCalls(page, "/rerun")).toBe(1);
    await page.waitForTimeout(1200);
    expect(await mockCalls(page, "/rerun")).toBe(1);
    await page.reload();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await page.waitForTimeout(1500);
    expect(await mockCalls(page, "/rerun")).toBe(0);
    await expect(page.getByTestId("plan-live")).toHaveText("Plan live");
  });

  test("an ordinary visit to the Desk starts nothing; other query parameters are kept", async ({ page }) => {
    await page.goto("/desk?x=1");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await page.waitForTimeout(1200);
    expect(await mockCalls(page, "/rerun")).toBe(0);
    await page.goto("/desk?x=1&plan=live");
    await expect(page.getByTestId("plan-live")).toHaveText("Planning live…");
    await expect(page).toHaveURL(/\/desk\?x=1$/);
    await expect.poll(() => mockCalls(page, "/rerun")).toBe(1); // the request follows the policy read
    await page.waitForTimeout(800);
    expect(await mockCalls(page, "/rerun")).toBe(1);
  });

  test("a 409 (a re-plan is already running) is shown as the Desk always shows it, with no second start", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/rerun": { kind: "conflict" } })));
    await page.goto("/desk?plan=live");
    await expect(page.getByText("A re-plan is already running")).toBeVisible(); // the one request was made and refused
    await page.waitForTimeout(1200);
    expect(await mockCalls(page, "/rerun")).toBe(1);
  });
});

test.describe("the Desk on a phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("?plan=live opens the flagship play's detail screen and starts the run once", async ({ page }) => {
    await page.goto("/desk?plan=live");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(page.getByTestId("plan-live")).toHaveText("Planning live…");
    await assertNoHorizontalOverflow(page);
    await expect.poll(() => mockCalls(page, "/rerun")).toBe(1);
    await page.waitForTimeout(800);
    expect(await mockCalls(page, "/rerun")).toBe(1);
  });
});

test.describe("the one-line loop strip above the decision", () => {
  const WORDS = ["Spot", "Plan", "Approve", "Offer", "Measure"];

  for (const [w, h] of [[1280, 800], [768, 900], [700, 900], [640, 900], [375, 812], [360, 780]] as const) {
    test(`${w} wide: the strip sits under the subline and above the first decision`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h });
      await page.goto("/");
      const strip = page.getByTestId("loop-strip");
      await expect(strip).toBeVisible();
      await expect(strip).toHaveAttribute("role", "img");
      await expect(strip).toHaveAttribute("aria-label", /Spot, Plan, Approve, Offer, Measure/);
      await expect(strip).toContainText("priors update");
      for (const word of WORDS) await expect(strip).toContainText(word);
      await expect(strip).not.toContainText(/Forecast|Propose/); // the SVG's words are not used here
      const target = w >= 768 ? page.locator(".hero").first() : page.getByTestId("feed-card-1");
      const [sub, box, below] = await settledRects(page.getByTestId("hero-subline"), strip, target);
      expect(box.y).toBeGreaterThanOrEqual(sub.y + sub.height - 1);
      expect(box.y + box.height).toBeLessThanOrEqual(below.y + 1);
      await assertNoHorizontalOverflow(page);
    });
  }

  test("a desktop strip is one line, at most 28 px tall", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const [box] = await settledRects(page.getByTestId("loop-strip"));
    expect(box.height).toBeLessThanOrEqual(28);
  });

  test("360 wide: still one line", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.goto("/");
    const [box] = await settledRects(page.getByTestId("loop-strip"));
    expect(box.height).toBeLessThanOrEqual(28);
  });

  test("it is not interactive: no buttons, links or tab stops", async ({ page }) => {
    await page.goto("/");
    const strip = page.getByTestId("loop-strip");
    await expect(strip.getByRole("button")).toHaveCount(0);
    await expect(strip.getByRole("link")).toHaveCount(0);
    expect(await strip.evaluate((el) => el.querySelectorAll("a, button, [tabindex]").length)).toBe(0);
  });

  test("no second compact loop: the old phone block is gone", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await expect(page.getByTestId("loop-strip")).toBeVisible();
    await expect(page.getByTestId("loop-compact")).toHaveCount(0);
    await expect(page.getByTestId("loop-diagram")).toBeHidden();
  });

  test("1280 wide: the detailed diagram is still under the decision", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("loop-diagram")).toBeVisible();
    const [card, diagram] = await settledRects(page.locator(".hero").first(), page.getByTestId("loop-diagram"));
    expect(diagram.y).toBeGreaterThanOrEqual(card.y + card.height - 1);
  });

  test("700 wide: strip above, detailed diagram below", async ({ page }) => {
    await page.setViewportSize({ width: 700, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("loop-strip")).toBeVisible();
    await expect(page.getByTestId("loop-diagram")).toBeVisible();
  });

  test("the primary action stays above the fold at 1280x800", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const [btn] = await settledRects(page.getByRole("button", { name: "Run the 60-second beat" }));
    expect(btn.y + btn.height).toBeLessThanOrEqual(800);
  });

  test("the strip goes away with the decision open on a desktop, so Approve keeps its place", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("beat-panel")).toBeVisible();
    await expect(page.getByTestId("loop-strip")).toBeHidden();
  });
});

test.describe("axe", () => {
  for (const scheme of ["light", "dark"] as const) {
    for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 375, height: 812 }]] as const) {
      test(`${scheme} ${name}: the landing with the secondary action / the loop strip`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.emulateMedia({ reducedMotion: "reduce", colorScheme: scheme });
        await withBackend(page, "vertex");
        await page.goto("/");
        await expect(page.getByTestId(name === "desktop" ? "watch-plan-live" : "loop-strip")).toBeVisible();
        if (name === "desktop") await expect(page.getByTestId("plan-eval-chip")).toBeVisible();
        await page.waitForTimeout(400);
        const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        const severe = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
      });
    }
  }
});

test("on the scripted backend the pass-rate chip does not name the model", async ({ page }) => {
  await withBackend(page, "stub");
  await page.goto("/");
  const chip = page.getByTestId("plan-eval-chip");
  await expect(chip).toHaveText("22/24 live plans passed (11 Oct), p50 26.5 s · committed eval");
  await expect(chip).not.toContainText("gemini");
});
