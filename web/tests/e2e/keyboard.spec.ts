import { expect, test, type Page } from "@playwright/test";

// Keyboard-only walk of the judge path (design_spec.md 9.2): the skip link is the first tab stop,
// every stop shows a focus ring, nothing traps focus, a control that removes itself hands focus on,
// and the Reset dialog returns focus to the button that opened it.

interface Stop {
  tag: string;
  name: string;
  ring: boolean;
  visible: boolean;
}

async function stop(page: Page): Promise<Stop | null> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return null;
    const cs = getComputedStyle(el);
    const ring = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow !== "none" && cs.boxShadow !== "");
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      name: (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60),
      ring,
      visible: r.width > 0 && r.height > 0,
    };
  });
}

/** Tabs through the page once and returns every stop. Stops at the first return to the skip link or the browser. */
async function tabAround(page: Page, max = 90): Promise<Stop[]> {
  const stops: Stop[] = [];
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const s = await stop(page);
    if (!s) break; // focus left the page: the cycle is complete
    if (s.tag === "nextjs-portal") continue; // the dev server's own overlay, not part of the app
    if (i > 0 && s.name === "Skip to main content") break;
    stops.push(s);
  }
  return stops;
}

const ROUTES = ["/", "/desk", "/phone", "/chat", "/outcomes"];

for (const route of ROUTES) {
  test(`${route}: skip link first, a ring on every stop, and focus leaves the page (no trap)`, async ({ page }) => {
    await page.goto(route);
    await page.waitForTimeout(900);
    const stops = await tabAround(page);
    expect(stops[0].name).toBe("Skip to main content");
    expect(stops[0].visible).toBe(true);
    expect(stops.length).toBeGreaterThan(5);
    expect(stops.length).toBeLessThan(90); // the cycle ended before the cap: not a trap
    const noRing = stops.filter((s) => !s.ring).map((s) => s.name);
    expect(noRing, `stops without a visible focus ring: ${noRing.join(" | ")}`).toEqual([]);
    const hidden = stops.filter((s) => !s.visible).map((s) => s.name);
    expect(hidden, `focus on something with no size: ${hidden.join(" | ")}`).toEqual([]);
  });

  test(`${route}: the skip link jumps to the main region`, async ({ page }) => {
    await page.goto(route);
    await page.waitForTimeout(500);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#main-content")).toBeFocused();
    // the next Tab lands inside the page content, past the brand and the stepper
    await page.keyboard.press("Tab");
    const inMain = await page.evaluate(() => Boolean(document.activeElement?.closest("main")));
    expect(inMain).toBe(true);
  });
}

test("landing: Reset demo data is the last stop in the page's own tab order", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(900);
  const stops = await tabAround(page);
  const names = stops.map((s) => s.name);
  expect(names[names.length - 1]).toBe("Reset demo data");
});

test("landing: Run the beat, Approve and read the result using only the keyboard", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(700);
  const cta = page.getByRole("button", { name: /60-second beat/ });
  await cta.focus();
  await page.keyboard.press("Enter");
  const panel = page.getByTestId("beat-panel");
  await panel.getByRole("button", { name: "Approve" }).waitFor();
  // the button that was pressed is gone: focus is on the card's title, not on <body>
  await expect(panel.locator("[data-card-title]")).toBeFocused();
  // Approve is reachable by Tab alone and is activated with Enter
  let reached = false;
  for (let i = 0; i < 8 && !reached; i++) {
    await page.keyboard.press("Tab");
    reached = await page.evaluate(() => (document.activeElement?.textContent ?? "").trim() === "Approve");
  }
  expect(reached).toBe(true);
  await page.keyboard.press("Enter");
  await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
  // focus moves to the result heading
  await expect(page.locator('[data-testid="approve-result"] h4').first()).toBeFocused();
  // the follow-ups are the next stops
  const seen: string[] = [];
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Tab");
    seen.push((await stop(page))?.name ?? "");
  }
  expect(seen.join(" | ")).toContain("Chat as Meena");
});

test("the Reset dialog traps Tab inside it, closes on Escape and returns focus to its button", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(700);
  const reset = page.getByRole("button", { name: "Reset demo data" });
  await reset.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press("Tab");
    const inside = await page.evaluate(() => {
      const a = document.activeElement;
      return a === document.body || Boolean(a?.closest("dialog"));
    });
    expect(inside).toBe(true); // never reaches the page behind the dialog
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(reset).toBeFocused();
});

test("chat: type, send with Enter, read the reply and toggle the English line, all from the keyboard", async ({ page }) => {
  await page.goto("/chat");
  const input = page.getByLabel("Message");
  await input.focus();
  await page.keyboard.press("Enter"); // pre-filled "Any offers today?"
  const log = page.getByTestId("chat-log");
  await expect(log.locator(".chat-msg--agent").first()).toBeVisible({ timeout: 10_000 });
  // the recorded offer is English, so the English line belongs to the Kannada order reply that follows "Add to cart"
  await log.locator(".chat-msg--agent").first().getByRole("button", { name: "Add to cart" }).focus();
  await page.keyboard.press("Enter");
  await expect(log.locator(".chat-msg--agent")).toHaveCount(2, { timeout: 10_000 });
  // Show/Hide English is a real button in the tab order, with its state announced
  const toggle = log.getByTestId("gloss-toggle").first();
  await toggle.focus();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
});

test.describe("phone: the two-screen Desk keeps focus", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("opening a play focuses its card; Back returns to the row that was open", async ({ page }) => {
    await page.goto("/desk");
    const row = page.getByLabel("Play inbox").getByRole("button").first();
    await row.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("play-detail").locator("[data-card-title]")).toBeFocused();
    await page.getByRole("button", { name: /Back to inbox/ }).focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('.inbox__item[aria-current="true"]')).toBeFocused();
  });
});

test.describe("an error card that goes away hands focus on", () => {
  test("Retry on the beat's error card leaves focus in the page, not on <body>", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("taal_mock_fault", JSON.stringify({ "/gaps": { kind: "network" } })));
    await page.goto("/");
    await page.getByRole("button", { name: /60-second beat/ }).click();
    const retry = page.getByTestId("error-card").getByTestId("error-retry");
    await retry.focus();
    await page.evaluate(() => localStorage.removeItem("taal_mock_fault"));
    await page.keyboard.press("Enter");
    await page.getByTestId("beat-panel").waitFor();
    const onBody = await page.evaluate(() => document.activeElement === document.body);
    expect(onBody).toBe(false);
  });
});
