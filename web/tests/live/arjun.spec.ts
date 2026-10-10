import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, shot, visitorHeaders } from "./helpers";

test.describe("Arjun: Play Desk", () => {
  test("inbox, play card, trace, why, edit, approve, policy re-plan", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-arjun");
    await page.goto("/desk");
    await expect(page.getByRole("heading", { name: "Play Desk" })).toBeVisible();
    const inbox = page.getByLabel("Play inbox");
    await expect(inbox.locator(".inbox__item").first()).toBeVisible();
    await shot(page, "arjun-01-inbox");

    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    // The decision card first (eyebrow, why now, figure, bars, plan, checks, Approve), then the
    // Desk-only sections; the rest is inside the card's Details.
    for (const h of ["Masala Chips 200G", "What Taal will do", "Copy", "Trace", "Policy"]) {
      await expect(card.getByRole("heading", { name: h, exact: true })).toBeVisible();
    }
    await expect(card.getByLabel("Holdout fraction")).toBeVisible();
    await card.getByTestId("card-details").locator("summary").click();
    await expect(card.getByRole("heading", { name: "Expected result" })).toBeVisible();
    await expect(card.getByLabel("Rationale")).toBeVisible();
    await expect(card.getByText(/est-v1/).first()).toBeVisible();
    // the checks are summarised on one line; opening it lists each rule by its plain name
    await card.getByTestId("guardrail-summary").click();
    await expect(card.getByText("Margin floor").first()).toBeVisible();
    await expect(card.getByText("9,200").first()).toBeVisible();
    await shot(page, "arjun-02-play-card");

    // "Why this play" (rationale and the alternatives the planner rejected) is in Details, already open
    // The flagship play is seeded from a real, committed Gemini recording (2026-09-28); the
    // model's own rejected alternative is a transfer, not a coupon (that was the old scripted
    // stub's story), rejected for negative expected margin.
    await expect(card.getByText(/transfer|negative expected margin/).first()).toBeVisible();
    await expect(card.getByText(/margin floor|margin_floor/i).first()).toBeVisible();
    await shot(page, "arjun-03-why");

    // trace is readable to a judge: invocation_id visible, one line per tool call, the revision visible
    await expect(card.locator(".trace-panel__event").first()).toBeVisible();
    await expect((await card.locator(".trace-panel__event").count())).toBeGreaterThan(3);
    await expect(card.getByText(/^e-[0-9a-f-]+$/).first()).toBeVisible();
    // The committed recording (2026-10-10, regenerated with the economics change) was rejected once,
    // by the schema check (an `id` key where `play_id` is required), then passed on attempt 2.
    await expect(card.locator(".trace-panel").getByText(/Additional properties are not allowed/).first()).toBeVisible();
    // ... and the panel lists those attempts: one rejected by the schema guardrail with its two
    // reasons and the wording that failed, then the one that passed.
    const attempts = card.locator(".trace-panel").getByTestId("trace-attempts");
    await expect(attempts.locator(".trace-attempt--rejected")).toHaveCount(1);
    await expect(attempts.locator(".trace-attempt--rejected").first().locator("code")).toHaveText(["schema", "schema"]);
    await expect(attempts.locator(".trace-attempt--rejected").first()).toContainText("'play_id' is a required property");
    await expect(attempts.locator(".trace-attempt--accepted")).toHaveCount(1);
    await shot(page, "arjun-03b-attempts");

    // replay reproduces the same panel state as the live run, event for event (snapshot diff)
    const trace = card.locator(".trace-panel__list");
    const beforeReplay = await trace.innerText();
    // The committed recording took 27.5 s wall time; at 4x replay that is ~7 s, inside the timeout below.
    await card.getByRole("button", { name: /Replay at 4x/ }).click();
    await expect(card.getByRole("button", { name: "Replay at 4x" })).toBeVisible({ timeout: 25_000 });
    const afterReplay = await trace.innerText();
    expect(afterReplay).toBe(beforeReplay);

    // edit the rationale, then approve: the play records the edit
    const ta = card.getByLabel("Rationale");
    await ta.fill("Approved for the Friday rush. 368 units at risk, ₹9200 write-off if we do nothing.");
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(page.locator("svg.forecast-chart")).toBeVisible({ timeout: 30_000 });
    // The outcome is announced by the panel's one persistent status region (#approve-live), and
    // screen-reader focus moves to the result's heading (ApprovePanel.tsx).
    const approveResult = page.getByTestId("approve-result");
    await expect(page.locator("#approve-live")).toHaveAttribute("role", "status");
    await expect(page.locator("#approve-live")).toContainText("Approved. Recovered versus doing nothing", { timeout: 15_000 });
    await expect(approveResult.getByRole("heading", { name: /Approved/ })).toBeFocused();
    await shot(page, "arjun-04-approved");

    // policy beat on the tea play
    await inbox.getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    await expect(card.getByText("Transfer stock, then nudge customers").first()).toBeVisible();
    const policy = card.locator("textarea").last();
    const text = await policy.inputValue();
    await policy.fill(text.replace("; prefer transfers for premium tea", ""));

    // POST /rerun now answers in 202 almost immediately and the planner keeps running after that
    // (services/api/main.py); a stub run can finish in a second or two, which would race past the
    // live-replan panel before this test could ever observe it. Delay the SSE stream's response
    // (fetch it for real, wait, then hand it back) so the panel is provably visible before the
    // eventual result, without fabricating any data -- every record the page receives is still the
    // real run's own trace.
    await page.route("**/events/*/stream", async (route) => {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ response });
    });

    await card.getByRole("button", { name: /Change policy/ }).click();
    await expect(page.getByTestId("live-replan")).toBeVisible();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 60_000 });
    await expect(card.getByText(/v2/).first()).toBeVisible();
    // ARIA status region for the re-plan result (web/app/desk/page.tsx)
    const replanResult = card.locator(".play-card__section").filter({ hasText: "Re-plan result" });
    await expect(replanResult).toHaveAttribute("role", "status");
    await shot(page, "arjun-05-replan");
    await expectNoConsoleErrors(errors);
  });

  test("Plan live runs the planner on the flagship gap and streams it into the trace", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-arjun-plan-live");
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    const recorded = card.locator(".trace-panel");
    await expect(recorded.getByTestId("trace-attempts")).toBeVisible();

    // hold the SSE response back so the panel is provably visible mid-run (see the policy beat above)
    await page.route("**/events/*/stream", async (route) => {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.fulfill({ response });
    });
    await card.getByTestId("plan-live").click();
    const liveRun = card.getByTestId("live-replan");
    await expect(liveRun).toBeVisible();
    await expect(liveRun.getByText(/\d+ s elapsed/)).toBeVisible();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 60_000 });
    await expect(recorded.getByTestId("trace-attempts").locator(".trace-attempt--rejected")).toHaveCount(1);
    // the streamed trace stays under the result once the run is done
    await expect(card.getByTestId("live-replan")).toHaveCount(0);
    await expect(card.getByTestId("live-trace").getByTestId("trace-attempts")).toBeVisible();
    // the live play sits in the inbox under the recorded one; the recorded play is still the one selected
    await expect(page.getByLabel("Play inbox").locator(".inbox__live")).toHaveCount(1);
    await expect(card.getByTestId("play-ids")).toContainText("play_chips_ds07_v1");
    const live = await (await page.request.get(`${API}/plays/play_chips_ds07_v1_live`, { headers: visitorHeaders("live-arjun-plan-live") })).json();
    expect(live.play_id).toBe("play_chips_ds07_v1_live");
    expect((await (await page.request.get(`${API}/plays/play_chips_ds07_v1`, { headers: visitorHeaders("live-arjun-plan-live") })).json()).source).toBe("recorded_gemini");
    await shot(page, "arjun-06-plan-live");
    await expectNoConsoleErrors(errors);
  });
});
