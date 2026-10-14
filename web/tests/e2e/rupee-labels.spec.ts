import { expect, test, type Page } from "@playwright/test";
import { reachedLine } from "../../lib/impact";
import { approveSettled, openBeat } from "./helpers";

// Final-week B3: every rupee figure sits inside an element that says what it rests on
// (data-basis = projected | synthetic | recorded | measured), and no bare LIVE badge sits over
// seeded-tenant figures. The offender list names the route and the text so a failure is actionable.

type Offender = { text: string; tag: string };

/** Every DOM text node that contains the rupee sign and has no [data-basis] ancestor. */
async function rupeeOffenders(page: Page): Promise<Offender[]> {
  return page.evaluate(() => {
    const out: { text: string; tag: string }[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const text = (n.nodeValue ?? "").trim();
      const el = n.parentElement;
      if (!text || !el || !text.includes("₹")) continue;
      if (["SCRIPT", "STYLE", "NOSCRIPT"].includes(el.tagName)) continue;
      if (el.closest("[data-basis]")) continue;
      out.push({ text: text.slice(0, 90), tag: `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.split(" ")[0] : ""}` });
    }
    return out;
  });
}

/** Elements whose own text is exactly LIVE, with whether their badge or card header also says SYNTHETIC. */
async function bareLive(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const bad: string[] = [];
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      const own = Array.from(el.childNodes)
        .filter((c) => c.nodeType === Node.TEXT_NODE)
        .map((c) => c.nodeValue ?? "")
        .join("")
        .trim();
      if (own !== "LIVE") continue;
      // The legend defines the word; it sits over no figures.
      if (el.closest("[data-testid='state-legend']")) continue;
      const badge = el.closest(".badge") ?? el.parentElement;
      const header = el.closest("header, .chat-panel__header, [data-testid='approve-result'], [data-testid='meena-preview']");
      const said = (badge?.textContent ?? "").includes("SYNTHETIC") || (header?.textContent ?? "").includes("SYNTHETIC");
      if (!said) bad.push((badge?.textContent ?? "LIVE").trim().slice(0, 80));
    }
    return bad;
  });
}

async function check(page: Page, route: string): Promise<void> {
  // let entrances and fetched data land before reading the DOM
  await page.waitForTimeout(600);
  const offenders = (await rupeeOffenders(page)).map((o) => `${route}: <${o.tag}> ${o.text}`);
  expect(offenders, "rupee text outside any [data-basis]").toEqual([]);
  const live = await bareLive(page);
  expect(live, `${route}: a bare LIVE badge with no SYNTHETIC beside it: ${live.join(" | ")}`).toEqual([]);
}

const approveButton = (page: Page) => page.getByTestId("approve-button").first();

test.describe("rupee figures carry a basis tag", () => {
  test("landing, first paint", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await check(page, "/ (first paint)");
  });

  test("landing, decision card open", async ({ page }) => {
    await openBeat(page);
    await expect(page.getByTestId("recovered-figure-amount").first()).toBeVisible();
    await check(page, "/ (decision card)");
  });

  test("landing, decision card with every Details section open", async ({ page }) => {
    await openBeat(page);
    const card = page.getByTestId("play-card");
    await expect(card).toBeVisible();
    for (const d of await card.locator("details > summary").all()) await d.click();
    await expect(card.getByTestId("rationale-text")).toBeVisible();
    await check(page, "/ (decision card, Details open)");
  });

  test("landing, after Approve", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await check(page, "/ (after Approve)");
  });

  test("desk, inbox", async ({ page }) => {
    await page.goto("/desk");
    await expect(page.getByLabel("Play inbox")).toBeVisible();
    await check(page, "/desk (inbox)");
  });

  test("desk, a play open", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await expect(page.getByTestId("play-detail")).toBeVisible();
    await check(page, "/desk (play open)");
  });

  test("desk, a play open with details expanded", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card).toBeVisible();
    for (const s of await card.locator("details > summary").all()) await s.click();
    await check(page, "/desk (play open, details expanded)");
  });

  test("desk, after Plan live finishes", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("plan-live").click();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 15_000 });
    await expect(card.getByTestId("live-trace")).toBeVisible();
    await check(page, "/desk (after Plan live)");
  });

  test("desk, after Approve", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("approve-button").click();
    await card.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await check(page, "/desk (after Approve)");
  });

  test("outcomes, before fast-forward", async ({ page }) => {
    await page.goto("/outcomes");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await check(page, "/outcomes (before fast-forward)");
  });

  test("outcomes, after fast-forward", async ({ page }) => {
    await page.addInitScript(() => {
      try {
        if (!window.sessionStorage.getItem("taal_seeded")) {
          window.localStorage.setItem("taal_mock_approved", JSON.stringify(["play_tea_ds04_v1"]));
          window.sessionStorage.setItem("taal_seeded", "1");
        }
      } catch {
        // storage blocked: the test fails on its own assertion
      }
    });
    await page.goto("/outcomes");
    await page.getByTestId("fast-forward-go").click();
    await expect(page.getByTestId("fast-forward-done")).toBeVisible({ timeout: 30_000 });
    await check(page, "/outcomes (after fast-forward)");
  });

  test("phone, with a sample pallet and the gap card", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await expect(page.getByTestId("intake-table")).toBeVisible();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await expect(page.getByTestId("why-now")).toBeVisible();
    await check(page, "/phone (gap card)");
    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    await check(page, "/phone (after Approve)");
  });

  test("chat, after an offer and an order", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    const log = page.getByTestId("chat-log");
    const offer = log.locator(".chat-msg--agent").first();
    await expect(offer).toContainText("₹");
    await check(page, "/chat (offer)");
    await offer.getByRole("button", { name: "Add to cart" }).click();
    await expect(log.locator(".chat-msg--agent")).toHaveCount(2);
    await check(page, "/chat (order)");
  });
});

test.describe("rupee figures carry a basis tag: phone width", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("landing feed, before and after Approve", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("feed-item-1")).toBeVisible();
    await check(page, "/ phone (feed)");
    await page.getByTestId("feed-item-1").getByTestId("approve-button").click();
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await check(page, "/ phone (feed, after Approve)");
  });

  test("desk inbox", async ({ page }) => {
    await page.goto("/desk");
    await expect(page.getByTestId("inbox-heading")).toBeVisible();
    await check(page, "/desk phone (inbox)");
  });
});

test.describe("Approve result copy", () => {
  test("states who was reached and who was held back, from the play's counts; no lift or CI before Measure", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    const result = page.getByTestId("approve-result");
    await expect(result.getByTestId("audience-chain")).toHaveText("Reached 355 customers, 39 held back; the lift is measured once orders arrive");
    await expect(result).not.toContainText(/response-rate difference|95% CI|lift:/i);
    await expect(result.getByTestId("basis-measured")).toHaveCount(0);
  });

  test("the line is built from treated_n and holdout_n, never fixed numbers", () => {
    expect(reachedLine({ treated_n: 316, holdout_n: 36 })).toBe("Reached 316 customers, 36 held back; the lift is measured once orders arrive");
  });
});

test.describe("badge legend", () => {
  test("says what LIVE, REPLAY and SYNTHETIC mean", async ({ page }) => {
    await page.goto("/");
    const legend = page.getByTestId("state-legend");
    await legend.locator("summary").click();
    await expect(legend).toContainText("This call ran on the service just now.");
    await expect(legend).toContainText("A recorded run replayed.");
    await expect(legend).toContainText("The data is the seeded demo tenant (no real customers, no pilot).");
  });

  test("a call badge over the seeded tenant names the data", async ({ page }) => {
    await page.goto("/chat");
    const badge = page.locator("#chat-panel .chat-panel__badges .badge").first();
    await expect(badge).toContainText("SYNTHETIC data");
  });
});
