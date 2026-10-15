import { test, expect, type Page, type Route } from "@playwright/test";
import { isSandboxRead } from "../../lib/session";
import { hasProgress, EMPTY_CRUMBS } from "../../lib/progress";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson } from "./helpers";

// A returning visitor whose browser still holds an old visitor id after the API restarted or the
// sandbox was reset. The app heals the session on its own: it starts a new sandbox (a new visitor id,
// the old progress forgotten) and carries on, showing at most one calm note. It never shows a restart
// banner and the "Waking the demo" notice at the same time, and the Waking notice is gone once the
// first read has settled. The fake API answers 404 on /plays for the old visitor id, as a sandbox
// that is gone does, and normally for any other id.

const STALE_ID = "v-stale-sandbox";
const NOTE = "Your demo session was restarted, so we began a new one for you.";
const VIEWPORTS = [
  { name: "1280", width: 1280, height: 800 },
  { name: "375", width: 375, height: 812 },
] as const;

/** The crumbs of a visitor who approved the hero play last time. */
async function seedReturningVisitor(page: Page, opts: { approved: boolean }) {
  await page.addInitScript(
    ({ id, approved }) => {
      try {
        // Only the first load: after the app has moved to a new id a reload must not put the old one back.
        if (window.localStorage.getItem("taal_visitor")) return;
        window.localStorage.setItem("taal_visitor", id);
        window.localStorage.setItem(
          `taal_progress:${id}`,
          JSON.stringify({
            spot: approved,
            plan: approved,
            offer: false,
            approved: approved ? [{ play_id: "play_tea_ds04_v1", gap_id: "gap_tea_ds04", at: "2026-09-12T03:30:00Z" }] : [],
            fastForwarded: [],
          }),
        );
      } catch {
        // storage blocked: the test fails on its own assertions
      }
    },
    { id: STALE_ID, approved: opts.approved },
  );
}

/** Records, for the whole page life, whether a restart note and a Waking notice were ever on screen together. */
async function watchForBothNotices(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __both: boolean; __sawNote: boolean };
    w.__both = false;
    w.__sawNote = false;
    const check = () => {
      const note = document.querySelector('[data-testid="sandbox-banner"]');
      const waking = document.querySelector('[data-testid="waking-notice"]');
      if (note) w.__sawNote = true;
      if (note && waking) w.__both = true;
    };
    new MutationObserver(check).observe(document, { childList: true, subtree: true });
    const loop = () => {
      check();
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  });
}

const visitorHeader = (route: Route) => route.request().headers()["x-taal-visitor"];

/** /plays, /outcomes and /customers/demo answer 404 for the old id and normally for any other. */
function staleSandboxApi(seen: { ids: Set<string> }) {
  const gone = (name: string) => async (route: Route) => {
    const id = visitorHeader(route);
    if (id) seen.ids.add(id);
    if (id === STALE_ID) {
      await route.fulfill({
        status: 404,
        headers: {
          "access-control-allow-origin": `http://localhost:${process.env.PORT || 3100}`,
          "access-control-allow-credentials": "true",
        },
        contentType: "application/json",
        body: JSON.stringify({ detail: "unknown sandbox" }),
      });
      return;
    }
    await okJson(mockFixture(name))(route);
  };
  return beatHandlers({ "/plays": gone("plays"), "/outcomes": gone("outcomes"), "/customers/demo": gone("customers_demo") });
}

async function readyState(page: Page, width: number) {
  if (width < 768) {
    await expect(page.getByTestId("feed-card-1")).toBeVisible({ timeout: 15_000 });
  } else {
    await expect(page.getByTestId("preview-figure")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toBeEnabled();
  }
}

for (const vp of VIEWPORTS) {
  test.describe(`stale session at ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("the sandbox is gone (404): a new session starts, the page is ready, no stuck notice, no Start again", async ({ page }) => {
      await seedReturningVisitor(page, { approved: true });
      await watchForBothNotices(page);
      await forceLiveApi(page, FAKE_API);
      const seen = { ids: new Set<string>() };
      await fakeApi(page, staleSandboxApi(seen));
      await page.goto("/");

      await readyState(page, vp.width);

      // a new visitor id was started, and the old one's progress is not carried over
      await expect.poll(() => page.evaluate(() => window.localStorage.getItem("taal_visitor"))).not.toBe(STALE_ID);
      const crumbs = await page.evaluate(() => {
        const id = window.localStorage.getItem("taal_visitor");
        return window.localStorage.getItem(`taal_progress:${id}`);
      });
      expect(crumbs === null || JSON.parse(crumbs).approved.length === 0).toBe(true);

      // let the first-read timers run out: nothing is stuck
      await page.waitForTimeout(2200);
      await expect(page.getByTestId("waking-notice")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Start again" })).toHaveCount(0);
      await expect(page.getByTestId("error-card")).toHaveCount(0);
      const both = await page.evaluate(() => (window as unknown as { __both: boolean }).__both);
      expect(both, "a restart note and a Waking notice were on screen together").toBe(false);
      expect(seen.ids.has(STALE_ID)).toBe(true);
      await assertNoHorizontalOverflow(page);
    });

    test("the sandbox answers but forgot the approval: crumbs cleared, one calm note, no Start again, steps open", async ({ page }) => {
      await seedReturningVisitor(page, { approved: true });
      await watchForBothNotices(page);
      await forceLiveApi(page, FAKE_API);
      // the fixture lists the hero play as "proposed": the browser says approved, the sandbox says not
      await fakeApi(page, beatHandlers({ "/outcomes": okJson(mockFixture("outcomes")) }));
      await page.goto("/");
      await readyState(page, vp.width);

      const note = page.getByTestId("sandbox-banner");
      await expect(note).toContainText(NOTE);
      await expect(note.getByRole("button")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Start again" })).toHaveCount(0);
      // the stepper is not locked behind a "start again"
      await expect(page.getByTestId("stepper").locator('li[data-state="locked"]').filter({ hasText: "Start again" })).toHaveCount(0);
      const crumbs = await page.evaluate(() => window.localStorage.getItem(`taal_progress:${"v-stale-sandbox"}`));
      expect(crumbs === null || JSON.parse(crumbs).approved.length === 0).toBe(true);

      // the note is brief: it goes by itself
      await expect(note).toHaveCount(0, { timeout: 15_000 });
      const both = await page.evaluate(() => (window as unknown as { __both: boolean }).__both);
      expect(both).toBe(false);
      await assertNoHorizontalOverflow(page);
    });

    test("a returning visitor with no progress heals silently: no note at all", async ({ page }) => {
      await seedReturningVisitor(page, { approved: false });
      await watchForBothNotices(page);
      await forceLiveApi(page, FAKE_API);
      const seen = { ids: new Set<string>() };
      await fakeApi(page, staleSandboxApi(seen));
      await page.goto("/");
      await readyState(page, vp.width);
      await page.waitForTimeout(2200);
      await expect(page.getByTestId("sandbox-banner")).toHaveCount(0);
      await expect(page.getByTestId("waking-notice")).toHaveCount(0);
      expect(await page.evaluate(() => (window as unknown as { __sawNote: boolean }).__sawNote)).toBe(false);
    });
  });
}

test.describe("stale session on the Desk", () => {
  test("the Desk heals too: the inbox fills and no notice is stuck", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await seedReturningVisitor(page, { approved: true });
    await watchForBothNotices(page);
    await forceLiveApi(page, FAKE_API);
    const seen = { ids: new Set<string>() };
    await fakeApi(page, {
      ...staleSandboxApi(seen),
      "/policy": okJson(mockFixture("policy")),
      "/events/run_tea_ds04_v1_e6b5d8f9": okJson(mockFixture("events")),
    });
    await page.goto("/desk");
    await expect(page.getByTestId("play-detail")).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(2200);
    await expect(page.getByTestId("waking-notice")).toHaveCount(0);
    await expect(page.getByTestId("error-card")).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { __both: boolean }).__both)).toBe(false);
  });
});

test.describe("the rules (pure)", () => {
  test("only the per-visitor reads can mean 'the sandbox is gone'", () => {
    for (const e of ["/plays", "/outcomes", "/customers/demo"]) expect(isSandboxRead(e, undefined)).toBe(true);
    expect(isSandboxRead("/plays", "get")).toBe(true);
    // an unknown gap, play, run or prior update is an ordinary 404; a write is never retried
    for (const e of ["/gaps/gap_x", "/plays/play_x", "/events/run_x", "/outcomes/prior_update", "/rerun/run_x", "/approve"]) {
      expect(isSandboxRead(e, undefined)).toBe(false);
    }
    expect(isSandboxRead("/plays", "POST")).toBe(false);
  });

  test("progress worth a word: any step done, or an approval", () => {
    expect(hasProgress(EMPTY_CRUMBS)).toBe(false);
    expect(hasProgress({ ...EMPTY_CRUMBS, spot: true })).toBe(true);
    expect(hasProgress({ ...EMPTY_CRUMBS, approved: [{ play_id: "p", gap_id: "g", at: "" }] })).toBe(true);
  });
});
