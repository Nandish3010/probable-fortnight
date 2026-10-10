import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { assertNoHorizontalOverflow, forgetMockApprovals, injectMockFaults, openBeat } from "./helpers";

// The stepper in the nav (components/Stepper.tsx): five linked steps with a persona caption each,
// states derived from /plays, /outcomes and localStorage crumbs, and the "demo restarted" banner.
// The rules are unit-tested in progress-units.spec.ts; the phone layout is in stepper-phone.spec.ts.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const stepper = (page: Page) => page.getByTestId("stepper");
const step = (page: Page, id: string) => stepper(page).locator(`li[data-step="${id}"]`);
const states = (page: Page) =>
  stepper(page)
    .locator("li")
    .evaluateAll((lis) => lis.map((li) => (li as HTMLElement).dataset.state));

const RESTARTED_TEXT = "Your demo session was restarted. Run the demo again from the start.";

/** A browser whose crumbs say the visitor approved the hero play (and so does nothing on the server). */
async function seedApprovedCrumb(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("taal_visitor", "v-restart");
    window.localStorage.setItem(
      "taal_progress:v-restart",
      JSON.stringify({
        spot: true,
        plan: true,
        offer: false,
        approved: [{ play_id: "play_tea_ds04_v1", gap_id: "gap_tea_ds04", at: "2026-09-12T03:30:00Z" }],
      }),
    );
  });
}

async function approveHero(page: Page) {
  const card = await openBeat(page);
  await card.getByRole("button", { name: "Approve" }).click();
  await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
}

test.describe("the stepper in the nav", () => {
  test("the brand is a link home; the five steps follow it, in order, with their persona", async ({ page }) => {
    await page.goto("/");
    const nav = page.locator("header.top-nav");
    await expect(nav.getByRole("link", { name: "Taal, home" })).toHaveAttribute("href", "/");
    const bar = page.getByRole("navigation", { name: "Progress" });
    await expect(bar).toBeVisible();
    await expect(bar.locator("ol > li")).toHaveCount(5);
    await expect(bar.locator('li [data-part="label"]')).toHaveText(["Spot", "Plan", "Approve", "Offer", "Measure"]);
    // the persona under the step, as text (no avatars in this phase); a locked step says what is missing instead
    await expect(step(page, "spot").locator('[data-part="caption"]')).toHaveText("Priya");
    await expect(step(page, "plan").locator('[data-part="caption"]')).toHaveText("Arjun");
    await expect(step(page, "approve").locator('[data-part="caption"]')).toHaveText("Arjun");
    await expect(step(page, "offer").locator('[data-part="caption"]')).toHaveText("Approve first");
    await expect(step(page, "measure").locator('[data-part="caption"]')).toHaveText("Approve first");
    // the old five text tabs are gone
    await expect(nav.getByText("Judge mode")).toHaveCount(0);
    await expect(nav.locator("a")).toHaveCount(6); // brand + five steps
    // the bar is one 56px row on a desktop
    expect((await nav.boundingBox())!.height).toBeLessThanOrEqual(57);
  });

  test("each step is a link to its screen, and its accessible name still says which screen", async ({ page }) => {
    await page.goto("/");
    const expected: [string, string][] = [
      ["Spot: Phone view (Priya)", "/phone"],
      ["Plan: Play Desk (Arjun)", "/desk"],
      ["Approve: Decision card (Arjun)", "/"],
      ["Offer: Chat (Meena), approve a plan first", "/chat"],
      ["Measure: Outcomes (Arjun), approve a plan first", "/outcomes"],
    ];
    for (const [name, href] of expected) {
      await expect(stepper(page).getByRole("link", { name })).toHaveAttribute("href", href);
    }
    // the destination names the old tabs used are still discoverable by name
    for (const old of ["Play Desk", "Phone view", "Chat", "Outcomes"]) {
      await expect(stepper(page).getByRole("link", { name: old })).toHaveCount(1);
    }
  });

  test("the screen you are on is the one current step, aria-current=step", async ({ page }) => {
    for (const [route, id] of [
      ["/", "approve"],
      ["/desk", "plan"],
      ["/phone", "spot"],
      ["/chat", "offer"],
      ["/outcomes", "measure"],
    ] as const) {
      await page.goto(route);
      const current = stepper(page).locator('[aria-current="step"]');
      await expect(current, route).toHaveCount(1);
      await expect(current).toHaveAttribute("href", route);
      await expect(step(page, id)).toHaveAttribute("data-state", "current");
    }
  });

  test("at the start Offer and Measure are locked with a hint, but they are still links that work", async ({ page }) => {
    await page.goto("/");
    await expect.poll(() => states(page)).toEqual(["next", "next", "current", "locked", "locked"]);
    const offer = step(page, "offer").getByRole("link");
    await expect(offer).toHaveAttribute("title", "Approve a plan first");
    await expect(offer).not.toHaveAttribute("aria-disabled", /./);
    await offer.click();
    await expect(page).toHaveURL(/\/chat$/);
    // ... and the chat is usable, locked step or not
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  test("a route off the path (feedback) gets the brand and a way back, not the stepper", async ({ page }) => {
    await page.goto("/feedback");
    await expect(page.getByTestId("stepper")).toHaveCount(0);
    await expect(page.locator("header.top-nav").getByRole("link", { name: "Back to demo" })).toHaveAttribute("href", "/");
  });

  test("Deck, Repo and Feedback are in the footer, on the landing and on the other screens", async ({ page }) => {
    for (const route of ["/", "/desk", "/chat"]) {
      await page.goto(route);
      const footer = page.locator("footer").last();
      await expect(footer.getByRole("link", { name: "Deck" })).toBeVisible();
      await expect(footer.getByRole("link", { name: "Repo" })).toBeVisible();
      await expect(footer.getByRole("link", { name: "Practitioner feedback" })).toHaveAttribute("href", "/feedback");
    }
  });
});

test.describe("ticks are derived, not stored on the server", () => {
  test("Approve ticks from /plays, which unlocks Offer; Plan is implied; the measured example counts once approved", async ({ page }) => {
    await approveHero(page);
    await expect(step(page, "approve")).toHaveAttribute("data-done", "true");
    await expect(step(page, "approve").locator('[data-icon="check"]')).toHaveCount(1); // current and done: ring plus tick
    await expect(step(page, "plan")).toHaveAttribute("data-state", "done");
    await expect(step(page, "offer")).toHaveAttribute("data-state", "next");
    await expect(step(page, "offer").locator('[data-part="caption"]')).toHaveText("Meena");
    await expect(step(page, "measure")).toHaveAttribute("data-state", "done"); // /outcomes has a measured row
    await expect(step(page, "spot")).toHaveAttribute("data-state", "next"); // never visited
  });

  test("the tick survives a reload and a trip to another screen, because /plays says approved", async ({ page }) => {
    await approveHero(page);
    await page.reload();
    await expect(step(page, "approve")).toHaveAttribute("data-done", "true");
    await step(page, "offer").getByRole("link").click();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(step(page, "approve")).toHaveAttribute("data-state", "done");
    await expect(step(page, "offer")).toHaveAttribute("data-state", "current");
  });

  test("an approval the server already has ticks Approve even with no crumbs in this browser", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_approved", JSON.stringify(["play_tea_ds04_v1"])));
    await page.goto("/");
    await expect(step(page, "approve")).toHaveAttribute("data-done", "true");
    await expect(page.getByTestId("sandbox-banner")).toHaveCount(0);
  });

  test("Spot ticks after Confirm rows on the phone view, and the crumb is read on the next screen", async ({ page }) => {
    await page.goto("/phone");
    await expect(step(page, "spot")).toHaveAttribute("data-done", "false");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await page.getByTestId("intake-table").waitFor();
    await expect(step(page, "spot")).toHaveAttribute("data-done", "false"); // a photo alone is not Spot
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await expect(step(page, "spot")).toHaveAttribute("data-done", "true");
    await page.goto("/");
    await expect(step(page, "spot")).toHaveAttribute("data-state", "done");
  });

  test("Offer ticks after a chat reply, once the plan is approved", async ({ page }) => {
    await approveHero(page);
    await step(page, "offer").getByRole("link").click();
    // the landing's own chat panel is still on screen until the /chat route has rendered, so wait for
    // the new page before touching Send (its customer picker would match the old panel too)
    await expect(page.getByRole("heading", { name: "Customer chat" })).toBeVisible();
    await expect(step(page, "offer")).toHaveAttribute("data-done", "false");
    await page.getByTestId("chat-customer-select").waitFor(); // the chat has hydrated: a click on Send will register
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("chat-log").locator(".chat-msg--agent").first()).toBeVisible();
    await expect(step(page, "offer")).toHaveAttribute("data-done", "true");
    await step(page, "approve").getByRole("link").click();
    await expect(step(page, "offer")).toHaveAttribute("data-state", "done");
  });

  test("a chat reply before any approval does not tick Offer", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("chat-log").locator(".chat-msg--agent").first()).toBeVisible();
    await expect(step(page, "offer")).toHaveAttribute("data-done", "false");
    await expect(step(page, "offer")).toHaveAttribute("data-state", "current");
  });

  test("opening the Desk ticks Plan", async ({ page }) => {
    await page.goto("/");
    await expect(step(page, "plan")).toHaveAttribute("data-state", "next");
    await page.goto("/desk");
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await expect(step(page, "plan")).toHaveAttribute("data-done", "true");
  });

  test("an unavailable /outcomes leaves Measure not done, not broken", async ({ page }) => {
    await injectMockFaults(page, { "/outcomes": { kind: "network" } });
    await page.addInitScript(() => window.localStorage.setItem("taal_mock_approved", JSON.stringify(["play_tea_ds04_v1"])));
    await page.goto("/");
    await expect(step(page, "approve")).toHaveAttribute("data-done", "true");
    await expect(step(page, "measure")).toHaveAttribute("data-done", "false");
    await expect(step(page, "measure")).toHaveAttribute("data-state", "next");
  });

  test("Reset demo data clears the visitor's progress", async ({ page }) => {
    await approveHero(page);
    await expect(step(page, "approve")).toHaveAttribute("data-done", "true");
    await page.getByRole("button", { name: "Reset demo data" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Reset", exact: true }).click();
    await expect(page.getByText(/Reset done for visitor/)).toBeVisible();
    await expect.poll(() => states(page)).toEqual(["next", "next", "current", "locked", "locked"]);
    const crumbs = await page.evaluate(() =>
      Object.keys(window.localStorage).filter((k) => k.startsWith("taal_progress:")),
    );
    expect(crumbs).toEqual([]);
  });

  test("two visitors in one browser do not share progress (the crumbs are namespaced by visitor id)", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("taal_visitor", "v-b");
      window.localStorage.setItem("taal_progress:v-a", JSON.stringify({ spot: true, plan: true, offer: true, approved: [] }));
    });
    await page.goto("/");
    await expect(step(page, "spot")).toHaveAttribute("data-done", "false");
  });
});

test.describe("sandbox restarted", () => {
  test("the crumbs say approved, /plays says proposed: one banner, the steps lock, Start again clears it", async ({ page }) => {
    await approveHero(page);
    await forgetMockApprovals(page); // the demo server restarted: it has forgotten the approval
    await page.reload();

    const banner = page.getByTestId("sandbox-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute("role", "status");
    await expect(banner).toContainText(RESTARTED_TEXT);
    await expect(page.getByTestId("sandbox-banner")).toHaveCount(1); // one banner, not one per component
    // everything but Spot is locked (and says so), and every step is still a link
    await expect.poll(() => states(page)).toEqual(["next", "locked", "current", "locked", "locked"]);
    await expect(step(page, "plan").locator('[data-part="caption"]')).toHaveText("Start again");
    await expect(step(page, "plan").getByRole("link")).toHaveAttribute("href", "/desk");
    // the card shows the play as it is on the server: not approved
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await expect(page.getByTestId("approve-button")).toBeVisible();

    await banner.getByRole("button", { name: "Start again" }).click();
    await expect(banner).toHaveCount(0);
    await expect.poll(() => states(page)).toEqual(["next", "next", "current", "locked", "locked"]);
    await page.reload();
    await expect(page.getByTestId("sandbox-banner")).toHaveCount(0);
  });

  test("a 404 from /plays for a visitor who had approved is the same state", async ({ page }) => {
    await seedApprovedCrumb(page);
    await injectMockFaults(page, { "/plays": { kind: "not_found" } });
    await page.goto("/chat");
    await expect(page.getByTestId("sandbox-banner")).toContainText(RESTARTED_TEXT);
    await expect(step(page, "approve").locator('[data-part="caption"]')).toHaveText("Start again");
  });

  test("no banner for a visitor who never approved, even when /plays is a 404", async ({ page }) => {
    await injectMockFaults(page, { "/plays": { kind: "not_found" } });
    await page.goto("/chat");
    await expect(stepper(page)).toBeVisible();
    await expect(page.getByTestId("sandbox-banner")).toHaveCount(0);
  });

  test("Approve answering 404 for a play the visitor approved shows the banner", async ({ page }) => {
    // The crumbs say approved; the server still lists it as approved, so the page offers no Approve
    // button. Reaching the 404 from Approve itself needs a card that still has the button: use the
    // Desk's chips play, approve it, then fail the next Approve of the same play.
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByRole("button", { name: "Approve" }).click();
    await card.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    // a later view of the same play after the server forgot it: Approve is offered again and answers 404
    await forgetMockApprovals(page);
    await page.evaluate(() => window.localStorage.setItem("taal_mock_fault", JSON.stringify({ "/approve": { kind: "not_found" } })));
    await page.reload();
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await page.getByTestId("play-detail").getByRole("button", { name: "Approve" }).click();
    await expect(page.getByTestId("approve-error")).toBeVisible();
    await expect(page.getByTestId("sandbox-banner")).toContainText(RESTARTED_TEXT);
  });
});

test.describe("stepper: accessibility and layout", () => {
  for (const scheme of ["light", "dark"] as const) {
    test.describe(scheme, () => {
      test.use({ colorScheme: scheme });

      test("axe: each state of the stepper (start, after Approve, restarted banner)", async ({ page }) => {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.goto("/");
        await page.waitForTimeout(300);
        let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(r.violations, "start: " + JSON.stringify(r.violations, null, 2)).toEqual([]);

        const card = await openBeat(page, { goto: false });
        await card.getByRole("button", { name: "Approve" }).click();
        await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
        await page.waitForTimeout(300);
        r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(r.violations, "approved: " + JSON.stringify(r.violations, null, 2)).toEqual([]);

        await forgetMockApprovals(page);
        await page.reload();
        await page.getByTestId("sandbox-banner").waitFor();
        await page.waitForTimeout(300);
        r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
        expect(r.violations, "restarted: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
      });
    });
  }

  test("keyboard: Tab reaches the brand, then the five steps in order, each with a visible focus ring", async ({ page }) => {
    await page.goto("/desk");
    await page.locator("header.top-nav a").first().focus();
    const labels: string[] = [];
    for (let i = 0; i < 6; i += 1) {
      labels.push(await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? ""));
      if (i === 1) {
        const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
        expect(outline).not.toBe("none");
      }
      await page.keyboard.press("Tab");
    }
    expect(labels[0]).toBe("Taal, home");
    expect(labels.slice(1).map((l) => l.split(":")[0])).toEqual(["Spot", "Plan", "Approve", "Offer", "Measure"]);
  });

  test("at 768 px the five steps fit the bar with their captions, none clipped", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 900 });
    await page.goto("/");
    await assertNoHorizontalOverflow(page);
    const clipped = await stepper(page).evaluate((nav) =>
      Array.from(nav.querySelectorAll<HTMLElement>('[data-part="label"], [data-part="caption"]')).filter((el) => el.scrollWidth > el.clientWidth + 0.5).length,
    );
    expect(clipped).toBe(0);
    const navBox = (await page.locator("header.top-nav").boundingBox())!;
    expect(navBox.height).toBeLessThanOrEqual(57);
  });
});
