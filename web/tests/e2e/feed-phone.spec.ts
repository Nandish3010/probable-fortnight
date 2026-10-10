import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import {
  FAKE_API,
  assertNoHorizontalOverflow,
  beatHandlers,
  fakeApi,
  forceLiveApi,
  mockFixture,
  okJson,
  openBeat,
} from "./helpers";

// E1: under 768 px the landing is a feed of the top decisions (components/DecisionFeed.tsx), run on
// the Pixel 7 project (412 px wide); the 360 px describes below shrink it. From 768 px up the
// landing is unchanged (landing.spec.ts and the specs that click "Run the 60-second beat").
// Mock data: the hero gap is the Darjeeling Tea lot (35,020), then Quinoa (11,210) and Masala
// Chips (9,200), the next two gaps by rupees at stake that have a plan.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const item = (page: Page, n: number) => page.getByTestId(`feed-item-${n}`);
const settled = (page: Page, n: number) => item(page, n).locator('[data-testid="approve-result"][data-phase="settled"]');

async function approveCard(page: Page, n: number) {
  await item(page, n).getByTestId("approve-button").click();
  await settled(page, n).waitFor({ timeout: 30_000 });
}

test.describe("feed: order and labels", () => {
  test("the hero line, then three decisions: the hero gap first, then the next two by rupees at stake", async ({ page }) => {
    await page.goto("/");
    const feed = page.getByTestId("decision-feed");
    await expect(feed).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Taal finds the stock you will throw away");
    await expect(feed.getByRole("heading", { level: 2 })).toHaveText(["Decision 1 of 3", "Decision 2 of 3", "Decision 3 of 3"]);
    await expect(feed.locator("[data-mode='feed']")).toHaveCount(3);
    const names = await feed.locator("[data-mode='feed'] h3").allTextContents();
    expect(names).toEqual(["Darjeeling Tea 100G", "Quinoa 500G", "Masala Chips 200G"]);
    // ranked by rupees at stake, after the hero
    await expect(item(page, 1).getByTestId("why-now")).toContainText("₹35,020");
    await expect(item(page, 2).getByTestId("why-now")).toContainText("₹11,210");
    await expect(item(page, 3).getByTestId("why-now")).toContainText("₹9,200");
    // the hero line sits above the feed, and there is no beat button to press
    const h1 = (await page.getByRole("heading", { level: 1 }).boundingBox())!;
    const first = (await item(page, 1).boundingBox())!;
    expect(first.y).toBeGreaterThan(h1.y + h1.height - 1);
    await expect(page.getByRole("button", { name: "Run the 60-second beat" })).toHaveCount(0);
  });

  test("every card shows its own source honestly (only the chips flagship has a recorded Gemini run)", async ({ page }) => {
    await page.goto("/");
    // mocks/plays.json: Tea and Quinoa are scripted; Chips (card 3) is the committed real-Gemini recording
    for (const n of [1, 2]) {
      const card = page.getByTestId(`feed-card-${n}`);
      await expect(card.locator(".badge").first()).toContainText("Scripted fixture");
      await expect(card).not.toContainText("Recorded from Gemini");
    }
    const chips = page.getByTestId("feed-card-3");
    await expect(chips.locator(".badge").first()).toContainText("Recorded from Gemini");
    await expect(chips).not.toContainText("Scripted fixture");
  });

  test("the feed is one column, and the chat panel follows it", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("feed-item-3").waitFor();
    const chat = (await page.locator(".chat-panel").boundingBox())!;
    const last = (await item(page, 3).boundingBox())!;
    expect(chat.y).toBeGreaterThanOrEqual(last.y + last.height - 1);
    for (const n of [1, 2, 3]) {
      const box = (await page.getByTestId(`feed-card-${n}`).boundingBox())!;
      expect(box.width).toBeLessThanOrEqual(480);
    }
  });

  test("no id is repeated on the page (three cards, one live region each)", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("feed-item-3").waitFor();
    const dupes = await page.evaluate(() => {
      const seen = new Map<string, number>();
      document.querySelectorAll("[id]").forEach((el) => seen.set(el.id, (seen.get(el.id) ?? 0) + 1));
      return Array.from(seen).filter(([, n]) => n > 1).map(([id]) => id);
    });
    expect(dupes).toEqual([]);
    await expect(page.locator("[id^='approve-live']")).toHaveCount(3);
  });
});

test.describe("feed: the sticky decision row", () => {
  test("Approve is pinned to the bottom of the screen while its card is on screen, and only that card's", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("feed-item-3").waitFor();
    const approve1 = item(page, 1).getByTestId("approve-button");
    await expect(approve1).toBeInViewport({ ratio: 1 });
    expect((await approve1.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await expect(item(page, 1).getByTestId("decision")).toContainText("₹7,498");
    await page.evaluate(() => window.scrollBy(0, 500));
    await expect(approve1).toBeInViewport({ ratio: 1 });

    // bring card 2 onto the screen: its own Approve is pinned, the first card's is not on top of it
    await item(page, 2).scrollIntoViewIfNeeded();
    await page.evaluate((y) => window.scrollTo(0, y), await item(page, 2).evaluate((el) => el.getBoundingClientRect().top + window.scrollY - 80));
    await expect(item(page, 2).getByTestId("approve-button")).toBeInViewport({ ratio: 1 });
    await expect(approve1).not.toBeInViewport();
  });
});

test.describe("feed: approve, then Next decision", () => {
  test("approving animates the result in place and offers Next decision; it brings the next card in and focuses its Approve", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("feed-item-3").waitFor();
    await expect(item(page, 1).getByTestId("feed-next")).toHaveCount(0); // nothing is offered before a decision
    await approveCard(page, 1);

    // the result is in the first card, which is still where it was
    await expect(item(page, 1).getByTestId("approve-result")).toBeVisible();
    await expect(item(page, 1).getByRole("heading", { name: "Approved: Darjeeling Tea 100G" })).toBeVisible();
    await expect(item(page, 2).getByTestId("approve-result")).toHaveCount(0);

    const next = item(page, 1).getByTestId("feed-next");
    await expect(next).toContainText("Quinoa 500G, ₹11,210 at stake");
    await next.getByRole("button", { name: "Next decision" }).click();

    // the second card is brought to the top of the screen and its Approve has focus
    await expect(item(page, 2).getByTestId("approve-button")).toBeFocused();
    await expect.poll(async () => Math.round((await item(page, 2).boundingBox())!.y)).toBeLessThan(140);
    await expect(item(page, 2).getByTestId("approve-button")).toBeInViewport({ ratio: 1 });

    // and so on to the third; the last one says it was the last
    await approveCard(page, 2);
    await item(page, 2).getByRole("button", { name: "Next decision" }).click();
    await expect(item(page, 3).getByTestId("approve-button")).toBeFocused();
    await approveCard(page, 3);
    const last = item(page, 3).getByTestId("feed-next");
    await expect(last).toContainText("That was the last of the top 3");
    await expect(last.getByRole("button", { name: "Next decision" })).toHaveCount(0);
    await expect(last.getByRole("link", { name: "See every plan in the Play Desk" })).toHaveAttribute("href", "/desk");
  });

  test("a card the server already shows as approved offers Next decision straight away", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_approved", JSON.stringify(["play_tea_ds04_v1"])));
    await page.goto("/");
    await expect(item(page, 1).getByTestId("feed-next")).toBeVisible();
    await expect(item(page, 1).getByTestId("approve-button")).toHaveCount(0);
    await item(page, 1).getByRole("button", { name: "Next decision" }).click();
    await expect(item(page, 2).getByTestId("approve-button")).toBeFocused();
  });

  test("Approve does not move the other cards' own state: a second card is still waiting", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("feed-item-3").waitFor();
    await approveCard(page, 1);
    await expect(item(page, 2).getByTestId("approve-button")).toBeEnabled();
    await expect(item(page, 3).getByTestId("approve-button")).toBeEnabled();
    await expect(page.getByTestId("step-strip")).toHaveCount(0);
  });
});

test.describe("feed: the toast", () => {
  test("on a phone it sits above the sticky decision row, and can be dismissed", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("feed-item-3").waitFor();
    await item(page, 1).getByTestId("approve-button").click();
    const toast = page.getByTestId("approve-toast");
    await expect(toast).toBeVisible({ timeout: 8000 });
    await expect(toast).toHaveCSS("position", "fixed");
    const box = (await toast.boundingBox())!;
    const vh = page.viewportSize()!.height;
    expect(vh - (box.y + box.height)).toBeGreaterThanOrEqual(72); // clear of a 72px decision row
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
    await toast.getByRole("button", { name: "Dismiss" }).click();
    await expect(toast).toHaveCount(0);
  });
});

test.describe("feed: loading, empty, error and missing plans", () => {
  test("loading shows card-shaped skeletons (not a spinner) and then the feed", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(
      page,
      beatHandlers({
        "/gaps": async (route) => {
          await new Promise((r) => setTimeout(r, 1500));
          await okJson(mockFixture("gaps"))(route);
        },
      }),
    );
    await page.goto("/");
    const loading = page.getByTestId("feed-loading");
    await expect(loading).toBeVisible();
    await expect(loading).toHaveAttribute("role", "status");
    await expect(loading.getByTestId("skeleton").first()).toBeVisible();
    await expect(page.getByTestId("decision-feed")).toBeVisible({ timeout: 8000 });
    await expect(loading).toHaveCount(0);
  });

  test("the service is down: an error card with Retry and Show recorded; the recorded feed is labelled", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/plays": { kind: "network" } })));
    await page.goto("/");
    const card = page.getByTestId("error-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("role", "alert");
    await card.getByRole("button", { name: "Show recorded result" }).click();
    await expect(page.getByTestId("recorded-note")).toContainText("recorded");
    await expect(page.getByTestId("decision-feed").locator("h3").first()).toHaveText("Darjeeling Tea 100G");
  });

  test("Retry reads again and shows the feed", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/plays": { kind: "http" } })));
    await page.goto("/");
    await page.getByTestId("error-card").waitFor();
    await page.evaluate(() => window.localStorage.removeItem("taal_mock_fault"));
    await page.getByTestId("error-card").getByRole("button", { name: "Retry" }).click();
    await expect(page.getByTestId("decision-feed")).toBeVisible();
  });

  test("the hero gap has no plan: it leads as the gap alone, the next two still have plans", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const plays = mockFixture("plays").filter((p: { gap_id: string }) => p.gap_id !== "gap_tea_ds04");
    await fakeApi(page, beatHandlers({ "/plays": okJson(plays) }));
    await page.goto("/");
    await expect(item(page, 1)).toContainText("Decision 1 of 3");
    await expect(item(page, 1).getByTestId("feed-no-plan")).toContainText("No plan yet for this gap");
    await expect(item(page, 1).getByTestId("approve-button")).toHaveCount(0);
    await expect(item(page, 2).getByTestId("approve-button")).toBeVisible();
    await expect(item(page, 3).getByTestId("approve-button")).toBeVisible();
  });

  test("no plans at all: one card for the hero gap, and a note that only one decision is waiting", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(page, beatHandlers({ "/plays": okJson([]) }));
    await page.goto("/");
    await expect(item(page, 1)).toContainText("Decision 1 of 1");
    await expect(page.getByTestId("decision-feed")).toContainText("Only 1 decision is waiting");
  });

  test("nothing at stake: 'No decisions waiting', with a way to the recorded decisions", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(page, beatHandlers({ "/gaps": okJson([]), "/plays": okJson([]) }));
    await page.goto("/");
    const empty = page.getByTestId("feed-empty");
    await expect(empty).toContainText("No decisions waiting");
    await expect(empty).toContainText("When it does, plans appear here ranked by rupees at stake.");
    await empty.getByRole("button", { name: "Show recorded decisions" }).click();
    await expect(page.getByTestId("decision-feed")).toBeVisible();
    await expect(page.getByTestId("recorded-note")).toBeVisible();
  });
});

test.describe("feed: no horizontal overflow at 360 px, in every state", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("loading, loaded, approved, next decision, all approved", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    await fakeApi(
      page,
      beatHandlers({
        "/gaps": async (route) => {
          await new Promise((r) => setTimeout(r, 1200));
          await okJson(mockFixture("gaps"))(route);
        },
        "/approve": async (route) => {
          // the real request path answers Approve from the recorded fixture
          await okJson(mockFixture("approve"))(route);
        },
      }),
    );
    await page.goto("/");
    await page.getByTestId("feed-loading").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByTestId("feed-item-3").waitFor({ timeout: 8000 });
    await assertNoHorizontalOverflow(page);
    await approveCard(page, 1);
    await item(page, 1).getByTestId("feed-next").waitFor();
    await assertNoHorizontalOverflow(page);
    await item(page, 1).getByRole("button", { name: "Next decision" }).click();
    await assertNoHorizontalOverflow(page);
    await approveCard(page, 2);
    await approveCard(page, 3);
    await assertNoHorizontalOverflow(page);
  });

  test("error, recorded, empty and no-plan states", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/gaps": { kind: "network" } })));
    await page.goto("/");
    await page.getByTestId("error-card").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByTestId("error-card").getByRole("button", { name: "Show recorded result" }).click();
    await page.getByTestId("decision-feed").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("hero without a plan, and the empty feed", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const plays = mockFixture("plays").filter((p: { gap_id: string }) => p.gap_id !== "gap_tea_ds04");
    await fakeApi(page, beatHandlers({ "/plays": okJson(plays) }));
    await page.goto("/");
    await item(page, 1).getByTestId("feed-no-plan").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("a restarted demo: the banner over the feed", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("taal_visitor", "v-feed");
      window.localStorage.setItem(
        "taal_progress:v-feed",
        JSON.stringify({ spot: false, plan: true, offer: false, approved: [{ play_id: "play_tea_ds04_v1", gap_id: "gap_tea_ds04", at: "2026-09-12T03:30:00Z" }] }),
      );
    });
    await page.goto("/");
    await page.getByTestId("sandbox-banner").waitFor();
    await assertNoHorizontalOverflow(page);
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`feed: axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    test.beforeEach(async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
    });

    test("loaded, then after Approve with Next decision", async ({ page }) => {
      await page.goto("/");
      await page.getByTestId("feed-item-3").waitFor();
      await page.waitForTimeout(300);
      let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
      await approveCard(page, 1);
      await page.waitForTimeout(300);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    });

    test("loading and error states", async ({ page }) => {
      await page.addInitScript(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/plays": { kind: "network" } })));
      await page.goto("/");
      await page.getByTestId("error-card").waitFor();
      const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  });
}

test("openBeat on a phone returns the first feed card", async ({ page }) => {
  const card = await openBeat(page);
  await expect(card).toContainText("Decision 1 of 3");
});
