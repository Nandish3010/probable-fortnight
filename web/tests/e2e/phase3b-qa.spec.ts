import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { assertNoHorizontalOverflow, injectMockFaults } from "./helpers";

// Phase 3B final QA for the two screens the earlier passes did not cover state by state: the chat
// and Outcomes. axe (WCAG 2.0/2.1 A and AA) in light and dark, desktop and phone; the 360 px
// overflow assertion in every state; the reduced-motion path; and a forced-colors sanity check.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

/** A browser whose crumbs say the visitor approved the chips play, which the mock outcomes have measured. */
async function seedApprovedChips(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("taal_visitor", "v-qa");
    window.localStorage.setItem(
      "taal_progress:v-qa",
      JSON.stringify({
        spot: true,
        plan: true,
        offer: true,
        approved: [{ play_id: "play_chips_ds07_v1", gap_id: "gap_chips_ds07", at: "2026-09-12T03:30:00Z" }],
      }),
    );
  });
}

type State = { name: string; open: (page: Page) => Promise<void> };

const STATES: State[] = [
  {
    name: "chat: empty",
    open: async (page) => {
      await page.goto("/chat");
      await page.getByTestId("chat-customer-select").waitFor();
    },
  },
  {
    name: "chat: Kannada reply with English shown and Sources open",
    open: async (page) => {
      await page.goto("/chat");
      await page.getByRole("button", { name: "Send" }).click();
      const offer = page.getByTestId("chat-log").locator(".chat-msg--agent").first();
      await offer.waitFor();
      await offer.getByTestId("chat-sources").locator("summary").click();
      await page.getByTestId("chat-customer-ids").locator("summary").click();
    },
  },
  {
    name: "chat: English fallback reply",
    open: async (page) => {
      await page.goto("/chat");
      await page.getByRole("button", { name: "Do you have Cola Zero?" }).click();
      await page.getByTestId("english-fallback-label").waitFor();
    },
  },
  {
    name: "chat: failed send with the error card",
    open: async (page) => {
      await injectMockFaults(page, { "/chat": { kind: "network" } });
      await page.goto("/chat");
      await page.getByRole("button", { name: "Send" }).click();
      await page.getByTestId("error-card").waitFor();
    },
  },
  {
    name: "outcomes: empty summary",
    open: async (page) => {
      await page.goto("/outcomes");
      await page.getByTestId("summary-empty").waitFor();
      await page.locator(".outcomes-table tbody tr").first().waitFor();
    },
  },
  {
    name: "outcomes: the visitor's measured result",
    open: async (page) => {
      await seedApprovedChips(page);
      await page.goto("/outcomes");
      await page.getByTestId("summary-difference").waitFor();
    },
  },
  {
    name: "outcomes: after Run Measure",
    open: async (page) => {
      await seedApprovedChips(page);
      await page.goto("/outcomes");
      await page.getByRole("button", { name: "Run Measure" }).click();
      await page.getByTestId("measure-result").waitFor();
    },
  },
  {
    name: "outcomes: the measure call failed",
    open: async (page) => {
      await injectMockFaults(page, { "/measure": { kind: "http" } });
      await page.goto("/outcomes");
      await page.getByRole("button", { name: "Run Measure" }).click();
      await page.getByTestId("error-card").waitFor();
    },
  },
];

for (const scheme of ["light", "dark"] as const) {
  for (const [vp, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 390, height: 844 }]] as const) {
    test.describe(`axe, ${scheme} ${vp}`, () => {
      test.use({ viewport, colorScheme: scheme });
      for (const state of STATES) {
        test(state.name, async ({ page }) => {
          await page.emulateMedia({ reducedMotion: "reduce" });
          await state.open(page);
          await page.waitForTimeout(300);
          const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
          expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
        });
      }
    });
  }
}

test.describe("no horizontal overflow at 360 px: chat and Outcomes", () => {
  test.use({ viewport: { width: 360, height: 800 } });
  for (const state of STATES) {
    test(state.name, async ({ page }) => {
      await state.open(page);
      await assertNoHorizontalOverflow(page);
    });
  }
  test("the Outcomes table stacks into cards under 768 px", async ({ page }) => {
    await page.goto("/outcomes");
    await page.locator(".outcomes-table tbody tr").first().waitFor();
    const display = await page.locator(".outcomes-table tbody tr").first().evaluate((el) => getComputedStyle(el).display);
    expect(display).toBe("flex");
    await expect(page.locator(".outcomes-table thead")).not.toBeInViewport();
  });
});

test.describe("reduced motion", () => {
  test("chat and Outcomes animate nothing: bubbles appear with no running animation", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const bubble = page.getByTestId("chat-log").locator(".chat-msg--agent").first();
    await bubble.waitFor();
    const ms = await bubble.evaluate((el) => parseFloat(getComputedStyle(el).animationDuration) * 1000);
    expect(ms).toBeLessThan(5);
    await page.goto("/outcomes");
    const anim = await page.getByTestId("outcome-summary").evaluate((el) => getComputedStyle(el).animationDuration);
    expect(parseFloat(anim) * 1000).toBeLessThan(5);
  });
});

test.describe("forced colors (Windows high contrast)", () => {
  for (const route of ["/", "/desk", "/chat", "/outcomes"]) {
    test(`${route}: no gradient-clipped text, focus is an outline, state words are text`, async ({ page }) => {
      await page.emulateMedia({ forcedColors: "active", colorScheme: "light" });
      await page.goto(route);
      await page.waitForTimeout(600);
      const clipped = await page.evaluate(() =>
        Array.from(document.querySelectorAll<HTMLElement>("body *"))
          .filter((el) => {
            const cs = getComputedStyle(el);
            const clip = cs.getPropertyValue("-webkit-background-clip") || cs.getPropertyValue("background-clip");
            return clip === "text" || cs.webkitTextFillColor === "transparent";
          })
          .map((el) => el.tagName + "." + el.className),
      );
      expect(clipped).toEqual([]);
      await page.keyboard.press("Tab");
      const ring = await page.evaluate(() => {
        const cs = getComputedStyle(document.activeElement as Element);
        return cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
      });
      expect(ring).toBe(true);
      // every badge says its state in words (LIVE, REPLAY, SYNTHETIC ...), not by colour alone
      const empty = await page.locator(".badge").evaluateAll((els) => els.filter((e) => !(e.textContent ?? "").trim()).length);
      expect(empty).toBe(0);
    });
  }
});
