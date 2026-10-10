import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import {
  FAKE_API,
  approveSettled,
  assertNoHorizontalOverflow,
  beatHandlers,
  clearMockFaults,
  fakeApi,
  forceLiveApi,
  injectMockFaults,
  mockCalls,
  forgetMockApprovals,
  mockFixture,
  okJson,
  openBeat,
  setMockDelay,
} from "./helpers";
import { inrSigned } from "../../lib/format";
import { playImpact } from "../../lib/impact";

// The Approve choreography (design_spec.md section 6) in a browser: the state machine's states on
// screen, the honest timer and steps, the count-up, the Meena preview, the follow-ups, the chart at
// its pixel width, the live region, the shortcut and the position of the button. Mock mode; slow
// routes come from lib/mockFaults.ts (taal_mock_delay), the real request path from fakeApi().

const TEA = mockFixture("plays").find((p: { play_id: string }) => p.play_id === "play_tea_ds04_v1");
const RECOVERED = inrSigned(playImpact(TEA).recovered_inr); // the canonical figure, from the same function the app uses

// On a phone the landing holds three cards; the first is the one these tests approve.
const approveButton = (page: Page) => page.getByTestId("approve-button").first();

test.describe("submitting: honest steps and timer", () => {
  test("all three steps are 'working' with a real timer until the response, then they tick", async ({ page }) => {
    await setMockDelay(page, { "/approve": 3600 });
    await openBeat(page);
    await expect(page.locator("#approve-live")).toHaveCount(1); // present before anything happens
    await approveButton(page).click();

    const steps = page.getByTestId("approve-step");
    await expect(steps).toHaveCount(3);
    await expect(steps.nth(0)).toContainText("Writing the offer");
    await expect(steps.nth(1)).toContainText("Re-forecasting with the play");
    await expect(steps.nth(2)).toContainText("Assigning the holdout");
    for (let i = 0; i < 3; i += 1) await expect(steps.nth(i)).toHaveAttribute("data-state", "working");
    await expect(approveButton(page)).toBeDisabled();
    await expect(approveButton(page)).toHaveText("Approving…");

    // the timer counts real seconds, and says the honest estimate
    const timer = page.getByTestId("approve-timer");
    await expect(timer).toHaveText(/^Working: 0 s\. This usually takes 10 to 13 s\.$/);
    await expect(timer).toHaveText(/^Working: 2 s\./, { timeout: 4000 });
    // still nothing ticked: ticking before the answer would be a fake progress bar
    for (let i = 0; i < 3; i += 1) await expect(steps.nth(i)).toHaveAttribute("data-state", "working");

    // the response: ticks land one after another, then the list folds into one line
    await expect(steps.nth(0)).toHaveAttribute("data-state", "done", { timeout: 6000 });
    await expect(steps.nth(2)).toHaveAttribute("data-state", "done");
    await expect(page.getByTestId("approve-steps-summary")).toContainText(/^Done in \d+(\.\d)? s: offer written, forecast updated, holdout set aside$/);
    await expect(page.getByTestId("approve-timer")).toHaveCount(0);
    await approveSettled(page);
  });

  test("the persistent live region announces submitting, each step, and the result", async ({ page }) => {
    await setMockDelay(page, { "/approve": 1500 });
    await openBeat(page);
    await page.evaluate(() => {
      const w = window as unknown as { __live: string[] };
      w.__live = [];
      const el = document.querySelector("#approve-live")!;
      new MutationObserver(() => w.__live.push(el.textContent ?? "")).observe(el, { childList: true, characterData: true, subtree: true });
    });
    const live = page.locator("#approve-live");
    await expect(live).toHaveAttribute("role", "status");
    await expect(live).toHaveAttribute("aria-live", "polite");
    await expect(live).toHaveAttribute("aria-atomic", "true");
    await approveButton(page).click();
    await approveSettled(page);
    const said = await page.evaluate(() => (window as unknown as { __live: string[] }).__live);
    expect(said).toContain("Approving. This usually takes 10 to 13 seconds.");
    for (const step of ["Writing the offer", "Re-forecasting with the play", "Assigning the holdout"]) expect(said).toContain(`${step}: done.`);
    const last = said[said.length - 1];
    expect(last).toMatch(/^Approved\. Recovered versus doing nothing: 7,498 rupees\. 291 customers will receive the offer; 32 are held back\.$/);
    // the order: submitting first, then the steps, then the result
    expect(said.indexOf("Approving. This usually takes 10 to 13 seconds.")).toBeLessThan(said.indexOf("Writing the offer: done."));
    expect(said.indexOf("Assigning the holdout: done.")).toBeLessThan(said.length - 1);
    // one region, still there
    await expect(page.locator("#approve-live")).toHaveCount(1);
  });

  test("a double click sends one request and the button cannot be pressed again", async ({ page }) => {
    await setMockDelay(page, { "/approve": 1500 });
    await openBeat(page);
    await approveButton(page).dblclick();
    await expect(approveButton(page)).toBeDisabled();
    await approveSettled(page);
    expect(await mockCalls(page, "/approve")).toBe(1);
  });

  test("an error shows the card with Retry, announces once through the alert, and Retry completes", async ({ page }) => {
    await injectMockFaults(page, { "/approve": { kind: "http", times: 1 } });
    await openBeat(page);
    await approveButton(page).click();
    const error = page.getByTestId("approve-error");
    await expect(error).toBeVisible();
    await expect(error.getByTestId("error-card")).toHaveAttribute("role", "alert");
    await expect(page.locator("#approve-live")).toHaveText(""); // the alert speaks; the polite region does not repeat it
    await expect(approveButton(page)).toBeEnabled();
    await error.getByRole("button", { name: "Retry" }).click();
    await approveSettled(page);
    await expect(page.getByTestId("approve-error")).toHaveCount(0);
    expect(await mockCalls(page, "/approve")).toBe(2);
  });
});

test.describe("T0: the result", () => {
  test("the count-up runs 0 to the canonical figure, ends exactly on it, with the delta chip and the heading", async ({ page }) => {
    await openBeat(page);
    await page.evaluate(() => {
      const w = window as unknown as { __amounts: string[]; __stop: boolean };
      w.__amounts = [];
      w.__stop = false;
      const loop = () => {
        const el = document.querySelector('[data-testid="approve-recovered-amount"]');
        const text = el?.textContent ?? "";
        const list = w.__amounts;
        if (el && list[list.length - 1] !== text) list.push(text);
        if (!w.__stop) requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    });
    await approveButton(page).click();
    await approveSettled(page);
    const amounts = await page.evaluate(() => {
      (window as unknown as { __stop: boolean }).__stop = true;
      return (window as unknown as { __amounts: string[] }).__amounts;
    });
    const toNumber = (t: string) => Number(t.replace(/[^\d-]/g, ""));
    expect(amounts[0]).toBe("₹0");
    expect(amounts.length).toBeGreaterThan(5); // it really counted
    expect(amounts[amounts.length - 1]).toBe(RECOVERED);
    const values = amounts.map(toNumber);
    for (let i = 1; i < values.length; i += 1) expect(values[i]).toBeGreaterThanOrEqual(values[i - 1]); // monotonic: no overshoot
    expect(Math.max(...values)).toBe(toNumber(RECOVERED));

    const result = page.getByTestId("approve-result");
    await expect(result.getByRole("heading", { name: "Approved: Darjeeling Tea 100G" })).toBeFocused();
    await expect(page.getByTestId("approve-recovered-delta")).toHaveText(`+${RECOVERED} vs doing nothing`);
    await expect(page.getByTestId("approve-recovered-delta")).toHaveCSS("opacity", "1");
    await expect(result.getByRole("heading").first()).not.toContainText("play_tea_ds04_v1"); // the id lives in Details
    await expect(result.getByTestId("approve-details")).not.toHaveAttribute("open", "");
    await result.getByTestId("approve-details").locator("summary").click();
    await expect(result.getByTestId("approve-details")).toContainText("play_tea_ds04_v1");
  });

  test("the toast says how many are held back, lasts 5 s, and can be dismissed", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    const toast = page.getByTestId("approve-toast");
    await expect(toast).toBeVisible({ timeout: 8000 });
    await expect(toast).toHaveText("Approved. Taal will hold back 32 customers to measure the result.");
    await expect(toast).not.toHaveAttribute("role", /./); // announced once, by #approve-live, not twice
    const shownAt = Date.now();
    await expect(toast).toBeHidden({ timeout: 8000 });
    expect(Date.now() - shownAt).toBeGreaterThan(4000);
    expect(Date.now() - shownAt).toBeLessThan(6500);

    // dismiss button on a second run (a fresh server: the first approval is forgotten)
    await forgetMockApprovals(page);
    await page.reload();
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await approveButton(page).click();
    await expect(page.getByTestId("approve-toast")).toBeVisible({ timeout: 8000 });
    await page.getByTestId("approve-toast").getByRole("button", { name: "Dismiss" }).click();
    await expect(page.getByTestId("approve-toast")).toHaveCount(0);
  });

  test("nothing above the result moves while it plays: the button's place, then the heading's place", async ({ page }) => {
    await setMockDelay(page, { "/approve": 800 });
    await openBeat(page);
    const docY = (testId: string) =>
      page.evaluate((id) => {
        const el = document.querySelector(`[data-testid="${id}"]`);
        return el ? Math.round(el.getBoundingClientRect().top + window.scrollY) : null;
      }, testId);
    const buttonY = await docY("approve-button");
    await approveButton(page).click();
    await expect(page.getByTestId("approved-bar")).toBeVisible({ timeout: 8000 });
    expect(await docY("approved-bar")).toBeGreaterThanOrEqual(buttonY! - 1);
    expect(await docY("approved-bar")).toBeLessThanOrEqual(buttonY! + 1);

    // the heading is where it will stay from the moment the body mounts to the end
    const heading = page.getByTestId("approve-result").getByRole("heading").first();
    await heading.waitFor();
    const first = await docY("approve-result");
    const samples: (number | null)[] = [];
    for (let i = 0; i < 12; i += 1) {
      samples.push(await docY("approve-result"));
      await page.waitForTimeout(120);
    }
    await approveSettled(page);
    samples.push(await docY("approve-result"));
    for (const y of samples) expect(Math.abs((y ?? 0) - (first ?? 0))).toBeLessThanOrEqual(1);
  });

  test("reduced motion: everything is there at once, the same information, no count-up, no slide", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openBeat(page);
    await approveButton(page).click();
    const result = page.getByTestId("approve-result");
    await expect(result).toBeVisible({ timeout: 8000 });
    // visible means final: no waiting for a sequence
    await expect(result).toHaveAttribute("data-phase", "settled");
    await expect(result).toHaveAttribute("data-motion", "off");
    await expect(result.getByTestId("approve-recovered-amount")).toHaveText(RECOVERED);
    await expect(result.getByTestId("approve-recovered-delta")).toHaveCSS("opacity", "1");
    await expect(page.getByTestId("approve-steps-summary")).toBeVisible();
    await expect(page.getByTestId("approve-toast")).toBeVisible(); // it carries information, so it still appears
    await expect(page.getByTestId("meena-preview")).toHaveAttribute("data-motion", "off");
    const chart = page.locator("svg.forecast-chart path").last();
    expect(await chart.evaluate((el) => getComputedStyle(el).animationName)).toBe("none");
    await expect(page.locator("#approve-live")).toContainText("Approved. Recovered versus doing nothing");
  });
});

test.describe("already approved", () => {
  test("a play the API says is approved shows the recorded result, 'Approved at HH:MM', and no animation", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const plays = mockFixture("plays").map((p: { play_id: string }) =>
      p.play_id === "play_tea_ds04_v1" ? { ...p, status: "approved", approved_at: "2026-09-12T03:42:00Z" } : p,
    );
    await fakeApi(page, beatHandlers({ "/plays": okJson(plays), "/chat": okJson(mockFixture("chat").greeting) }));
    await openBeat(page);
    await expect(page.getByTestId("already-approved-banner")).toHaveText("Already approved. Showing the recorded result.");
    await expect(page.getByTestId("approved-bar")).toHaveText("Approved at 09:12");
    await expect(page.getByTestId("approve-result")).toHaveAttribute("data-phase", "alreadyApproved");
    await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
    await expect(page.getByTestId("approve-steps")).toHaveCount(0);
    await expect(page.getByTestId("approve-toast")).toHaveCount(0);
    await expect(page.getByTestId("approve-recovered-amount")).toHaveText(RECOVERED);
    // opening the page does not steal focus
    await expect(page.getByRole("heading", { name: /^Approved:/ })).not.toBeFocused();
  });
});

test.describe("Meena preview", () => {
  test("shows the real first reply: Kannada with lang=kn, the English gloss beneath, slid in, never blocking the result", async ({ page }) => {
    await setMockDelay(page, { "/chat": 1800 });
    await openBeat(page);
    await approveButton(page).click();
    // the result is already there while the preview is still being written
    await expect(page.getByTestId("approve-result")).toBeVisible({ timeout: 8000 });
    const preview = page.getByTestId("meena-preview");
    await expect(preview).toHaveAttribute("data-status", "loading");
    await expect(preview).toContainText("Meena's message is being written…");
    await expect(preview).toHaveAttribute("data-motion", "on");

    const text = page.getByTestId("meena-text");
    await expect(text).toBeVisible({ timeout: 10_000 });
    await expect(text).toHaveAttribute("lang", "kn");
    await expect(text).toContainText("ಇಂದು");
    const gloss = page.getByTestId("meena-gloss");
    await expect(gloss).toHaveAttribute("lang", "en");
    await expect(gloss).toContainText("English: Offer: Masala Chips 200G with Coconut Water 1L");
    await expect(page.getByTestId("english-fallback-label")).toHaveCount(0);
    await expect(preview).toContainText("What Meena receives");

    // the English gloss can be hidden, and stays hidden
    await page.getByTestId("meena-gloss-toggle").click();
    await expect(page.getByTestId("meena-gloss")).toHaveCount(0);
    await expect(page.getByTestId("meena-gloss-toggle")).toHaveText("Show English");
  });

  test("a /chat failure shows 'Preview unavailable', keeps the result, and Try again recovers", async ({ page }) => {
    await injectMockFaults(page, { "/chat": { kind: "http" } });
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await expect(page.getByTestId("meena-unavailable")).toHaveText("Preview unavailable. The chat agent did not answer in time.");
    await expect(page.getByTestId("meena-text")).toHaveCount(0); // never placeholder text as if it were the message
    await expect(page.getByTestId("approve-recovered-amount")).toHaveText(RECOVERED);
    await clearMockFaults(page);
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.getByTestId("meena-text")).toContainText("ಇಂದು");
  });

  test("no answer within 8 s is 'Preview unavailable' too", async ({ page }) => {
    test.setTimeout(40_000);
    await setMockDelay(page, { "/chat": 12_000 });
    await openBeat(page);
    const clicked = Date.now();
    await approveButton(page).click();
    await approveSettled(page);
    await expect(page.getByTestId("meena-preview")).toHaveAttribute("data-status", "loading");
    await expect(page.getByTestId("meena-unavailable")).toBeVisible({ timeout: 12_000 });
    const waited = Date.now() - clicked;
    expect(waited).toBeGreaterThan(8500); // 8 s from T0, which is about a second in
    expect(waited).toBeLessThan(12_000);
  });

  test("an English reply to a Kannada customer is labelled 'English fallback'; a reply with no offer says Meena may not be in the audience", async ({ page }) => {
    await forceLiveApi(page, FAKE_API);
    const english = {
      session_id: "CUST-MEENA:web",
      role: "agent",
      language: "kn",
      text: "I don't have any offers for you right now. Is there anything else I can help you with?",
    };
    await fakeApi(
      page,
      beatHandlers({
        "/approve": okJson(mockFixture("approve")),
        "/chat": okJson([english]),
      }),
    );
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await expect(page.getByTestId("english-fallback-label")).toHaveText("English fallback");
    await expect(page.getByTestId("meena-text")).toHaveAttribute("lang", "en");
    await expect(page.getByTestId("meena-text")).toContainText("I don't have any offers for you right now.");
    await expect(page.getByTestId("meena-audience-note")).toHaveText("Meena may not be in this play's audience.");
  });
});

test.describe("follow-ups", () => {
  test("'Chat as Meena' scrolls to the chat panel, focuses the composer and pre-fills the message", async ({ page }) => {
    await openBeat(page);
    await page.getByTestId("chat-log").first().evaluate((el) => el.closest("#chat-panel")!.scrollIntoView());
    await approveButton(page).click();
    await approveSettled(page);
    await page.getByTestId("chat-as-customer").click();
    const input = page.getByLabel("Message");
    await expect(input).toBeFocused();
    await expect(input).toHaveValue("Any offers today?");
    await expect(page.locator("#chat-panel")).toBeInViewport();
  });

  test("'See what the holdout group sees' selects the holdout persona and sends the message", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await expect(page.getByTestId("chat-customer-select")).toBeVisible();
    await page.getByTestId("see-holdout").click();
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-00316");
    await expect(page.getByTestId("chat-customer-note")).toHaveText("Holdout: never receives this offer, even after the play is approved.");
    await expect(page.getByTestId("chat-log").locator(".chat-msg--customer")).toHaveText("Any offers today?");
    await expect(page.getByTestId("chat-log").locator(".chat-msg--agent").first()).toBeVisible({ timeout: 8000 });
  });

  test("on a page with no chat panel (the Desk) the holdout button opens /chat with the holdout selected", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("approve-button").click();
    await card.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await card.getByTestId("see-holdout").click();
    await expect(page).toHaveURL(/\/chat\?as=holdout/);
    await expect(page.getByTestId("chat-customer-select")).toHaveValue("CUST-00316");
    await expect(page.getByTestId("chat-log").locator(".chat-msg--customer").first()).toHaveText("Any offers today?");
  });

  test("the chat caption comes from the hero play, not from the word 'chips'", async ({ page }) => {
    await openBeat(page);
    const note = page.getByTestId("chat-customer-note");
    await expect(note).not.toContainText(/chips/i);
    await expect(note).toHaveText("Receives the offer once the play is approved.");
  });
});

test.describe("forecast chart", () => {
  async function chartAfterApprove(page: Page) {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await page.waitForTimeout(300);
  }

  for (const width of [1280, 360]) {
    test(`every label is at least 12 px at rendered size, none overlap, at ${width} px wide`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await chartAfterApprove(page);
      const report = await page.evaluate(() => {
        const svg = document.querySelector("svg.forecast-chart") as SVGSVGElement;
        const vb = svg.viewBox.baseVal;
        const rect = svg.getBoundingClientRect();
        const scale = rect.width / vb.width;
        const texts = Array.from(svg.querySelectorAll("text")).map((t) => {
          const r = t.getBoundingClientRect();
          return {
            text: t.textContent ?? "",
            px: parseFloat(getComputedStyle(t).fontSize) * scale,
            box: { l: r.left, t: r.top, r: r.right, b: r.bottom },
          };
        });
        const wrap = svg.parentElement!.getBoundingClientRect();
        return { scale, svgW: rect.width, wrapW: wrap.width, vbW: vb.width, texts, rect: { l: rect.left, r: rect.right } };
      });
      expect(report.scale).toBeCloseTo(1, 1); // drawn 1:1, so the 12 px labels are 12 px on screen
      expect(Math.abs(report.svgW - report.wrapW)).toBeLessThanOrEqual(2); // the container's measured width
      expect(report.texts.length).toBeGreaterThanOrEqual(8);
      for (const t of report.texts) {
        expect(t.px, `"${t.text}" is ${t.px}px`).toBeGreaterThanOrEqual(12);
        expect(t.text, "no ISO dates on the chart").not.toMatch(/\d{4}-\d{2}-\d{2}/);
        expect(t.box.l).toBeGreaterThanOrEqual(report.rect.l - 1);
        expect(t.box.r).toBeLessThanOrEqual(report.rect.r + 1);
      }
      const names = report.texts.map((t) => t.text);
      for (const label of ["Offer window", "With the play", "Without the play", "Extra units sold", "because of the play", "12 Sep", "9 Oct", "Units per day"]) {
        expect(names, `label ${label}`).toContain(label);
      }
      // the y axis has three ticks
      expect(report.texts.filter((t) => /^\d+(\.\d)?$/.test(t.text))).toHaveLength(3);
      // no two labels sit on top of each other
      for (let i = 0; i < report.texts.length; i += 1) {
        for (let j = i + 1; j < report.texts.length; j += 1) {
          const a = report.texts[i].box;
          const b = report.texts[j].box;
          const overlap = a.l < b.r - 1 && b.l < a.r - 1 && a.t < b.b - 1 && b.t < a.b - 1;
          expect(overlap, `"${report.texts[i].text}" overlaps "${report.texts[j].text}"`).toBe(false);
        }
      }
    });
  }

  test("it is an image with a text summary, and the Approve caption is the honest one", async ({ page }) => {
    await chartAfterApprove(page);
    const svg = page.locator("svg.forecast-chart");
    await expect(svg).toHaveAttribute("role", "img");
    const label = (await svg.getAttribute("aria-label")) ?? "";
    expect(label).toMatch(/^Forecast chart: units sold per day, 12 Sep to 9 Oct/);
    expect(label).toContain("The offer window runs 12 Sep");
    await expect(page.getByTestId("writeoff-line")).toHaveText("What-if write-off ₹35,186 → ₹28,659");
    await expect(page.getByTestId("writeoff-caption")).toHaveText("What-if forecast using the past promo lift. Not the play's own estimate.");
    await expect(page.getByTestId("writeoff-caption")).not.toContainText("1.6");
  });

  test("it follows its container: resizing the window redraws it at the new width", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await chartAfterApprove(page);
    const widthOf = () => page.locator("svg.forecast-chart").evaluate((el) => el.getBoundingClientRect().width);
    const wide = await widthOf();
    await page.setViewportSize({ width: 800, height: 900 }); // still the desktop layout: below 768 the landing is the feed
    await expect.poll(widthOf).toBeLessThan(wide - 100);
    const wrap = await page.getByTestId("forecast-chart").evaluate((el) => el.getBoundingClientRect().width);
    expect(Math.abs((await widthOf()) - wrap)).toBeLessThanOrEqual(2);
  });
});

test.describe("the keyboard shortcut A", () => {
  test("from inside the card it focuses Approve without pressing it; Enter confirms", async ({ page }) => {
    await openBeat(page);
    await page.getByTestId("guardrail-summary").focus();
    await page.keyboard.press("a");
    await expect(approveButton(page)).toBeFocused();
    expect(await mockCalls(page, "/approve")).toBe(0);
    await page.keyboard.press("Enter");
    await approveSettled(page);
    expect(await mockCalls(page, "/approve")).toBe(1);
  });

  test("not from outside the card, not with a modifier, not while typing in the chat", async ({ page }) => {
    await openBeat(page);
    await page.getByLabel("Message").fill("");
    await page.keyboard.type("a");
    await expect(page.getByLabel("Message")).toHaveValue("a");
    await expect(approveButton(page)).not.toBeFocused();

    await page.getByTestId("guardrail-summary").focus();
    await page.keyboard.press("Control+a");
    await page.keyboard.press("Shift+A");
    await expect(approveButton(page)).not.toBeFocused();
  });

  test("not inside an input in the card: the Desk's rationale editor keeps the letter", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await card.getByTestId("card-details").locator("summary").click();
    const editor = card.locator("textarea").first();
    await editor.focus();
    const before = await editor.inputValue();
    await page.keyboard.press("End");
    await page.keyboard.type("a");
    expect(await editor.inputValue()).toBe(`${before}a`);
    await expect(card.getByTestId("approve-button")).not.toBeFocused();
    // and from a summary in the same card it works
    await card.getByTestId("guardrail-summary").focus();
    await page.keyboard.press("a");
    await expect(card.getByTestId("approve-button")).toBeFocused();
  });

  test("the 'Press A' hint shows on hover or focus on a desktop, not before", async ({ page }) => {
    await openBeat(page);
    // opening the beat puts keyboard focus on the card's title (so a keyboard user is not dropped on
    // <body>), and the hint shows while focus is inside the card: take the focus away first
    await expect(page.getByTestId("play-card").locator("[data-card-title]")).toBeFocused();
    await page.evaluate(() => (document.activeElement as HTMLElement).blur());
    await page.mouse.move(2, 400); // away from the card
    const hint = page.getByTestId("approve-hint");
    await expect(hint).toHaveCSS("opacity", "0");
    await page.getByTestId("play-card").hover();
    await expect(hint).toHaveCSS("opacity", "1");
    await expect(hint).toContainText("Press A");
  });

  test("it does nothing once the play is approved", async ({ page }) => {
    await openBeat(page);
    await approveButton(page).click();
    await approveSettled(page);
    await page.getByTestId("guardrail-summary").focus();
    await page.keyboard.press("a");
    await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  });
});

test.describe("above the fold", () => {
  test("at 1280x800 the Approve button's top edge is at or above y=740", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openBeat(page);
    await page.waitForTimeout(500);
    const box = await approveButton(page).boundingBox();
    expect(box!.y).toBeLessThanOrEqual(740);
    await expect(approveButton(page)).toBeInViewport({ ratio: 0.5 });
  });

  test("at 375x812 Approve is reachable without scrolling, in the sticky bar", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await openBeat(page);
    await expect(approveButton(page)).toBeInViewport({ ratio: 1 });
    expect((await approveButton(page).boundingBox())!.height).toBeGreaterThanOrEqual(44);
  });
});

test.describe("bars: legend and note", () => {
  test("the legend lists only the colours drawn, the transfer cost has its own entry, the axis note is behind an info button", async ({ page }) => {
    await openBeat(page);
    const legend = page.getByTestId("bars-legend");
    // Tea is a transfer play with no volume-giveaway figure: transfer cost and write-off, nothing else
    await expect(legend.locator("li")).toHaveText(["transfer cost", "write-off"]);
    await expect(legend).not.toContainText("margin earned");
    await expect(legend).not.toContainText("given away");
    await expect(page.getByTestId("bars-info-note")).toHaveCount(0);
    const button = page.getByTestId("bars-info-button");
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await button.click();
    const note = page.getByTestId("bars-info-note");
    await expect(note).toContainText("Net margin retained (₹) - a projection from the estimator, not a measurement.");
    await expect(note).not.toContainText("--");
    await page.keyboard.press("Escape");
    await expect(note).toHaveCount(0);
    await expect(button).toBeFocused();
  });

  test("a sales play's legend shows margin earned instead of transfer cost", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const legend = page.getByTestId("play-detail").getByTestId("bars-legend");
    await expect(legend).toContainText("margin earned");
    await expect(legend).not.toContainText("transfer cost");
  });
});

test.describe("settled state: overflow and accessibility", () => {
  test("no horizontal overflow at 360 px with the result, the preview and the info note open", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await openBeat(page);
    await page.getByTestId("bars-info-button").first().click();
    await approveButton(page).click();
    await approveSettled(page);
    await expect(page.getByTestId("meena-text")).toBeVisible({ timeout: 8000 });
    await assertNoHorizontalOverflow(page);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`axe: ${scheme}, after Approve, with the preview and the toast`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await openBeat(page);
      await approveButton(page).click();
      await approveSettled(page);
      await expect(page.getByTestId("meena-text")).toBeVisible({ timeout: 8000 });
      await expect(page.getByTestId("approve-toast")).toBeVisible();
      await page.waitForTimeout(400);
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  }

  test("axe: the submitting state (steps and timer) in light", async ({ page }) => {
    await setMockDelay(page, { "/approve": 4000 });
    await openBeat(page);
    await approveButton(page).click();
    await expect(page.getByTestId("approve-timer")).toBeVisible();
    await page.waitForTimeout(400);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    await approveSettled(page);
  });
});
