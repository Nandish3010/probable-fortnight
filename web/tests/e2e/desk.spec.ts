import { test, expect } from "@playwright/test";

// Mock mode: no committed real-Gemini recording exists (harness/recorded_traces.py), so every
// seeded play -- the flagship (gap_chips_ds07) included -- has source "scripted_stub", and the
// re-plan flow below is served from web/mocks/rerun.json + rerun_events.json.
test.describe("Play Desk: provenance badges and the live re-plan flow", () => {
  test("flagship trace shows Scripted fixture; policy change streams a live re-plan to a result", async ({ page }) => {
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();

    const card = page.getByTestId("play-detail");
    const trace = card.locator(".trace-panel");
    await expect(trace.getByText("Scripted fixture")).toBeVisible();

    const liveReplan = page.getByTestId("live-replan");
    await expect(liveReplan).not.toBeVisible();

    await card.getByRole("button", { name: /Change policy/ }).click();

    // The live-replan panel appears immediately with its stub-backend header line and a ticking
    // elapsed counter, then streamed trace rows arrive one at a time (mocks/rerun_events.json's
    // frames, ~250ms apart -- see api.ts's streamRerun mock).
    await expect(liveReplan).toBeVisible();
    await expect(liveReplan.getByText("Scripted planner is running")).toBeVisible();
    await expect(liveReplan.getByText(/\d+ s elapsed/)).toBeVisible();
    await expect(liveReplan.locator(".trace-panel__event").first()).toBeVisible({ timeout: 5_000 });

    // Once the stream's terminal "done" frame lands, the result section replaces the live panel.
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    await expect(liveReplan).not.toBeVisible();
    const resultSection = card.locator(".play-card__section").filter({ hasText: "Re-plan result" });
    await expect(resultSection.getByText("Scripted fixture")).toBeVisible();
  });

  test("trace panel lists every propose_play attempt: the rejection with its guardrail, reason and rationale, then the pass", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const attempts = page.getByTestId("play-detail").locator(".trace-panel").getByTestId("trace-attempts");
    await expect(attempts).toBeVisible();

    const first = attempts.getByTestId("trace-attempt-1");
    await expect(first.locator(".trace-panel__marker--fail")).toContainText("rejected");
    await expect(first.locator("code")).toHaveText("margin_floor");
    await expect(first.getByText(/net margin 1\.96%/)).toBeVisible();
    const rejected = first.locator("details");
    await expect(rejected).not.toHaveAttribute("open", "");
    await rejected.locator("summary").click();
    await expect(rejected.getByText(/Masala Chips 200G at Dark store 07/)).toBeVisible();

    const second = attempts.getByTestId("trace-attempt-2");
    await expect(second.getByText("passed all guardrails")).toBeVisible();
  });

  test("Plan live streams a run into the trace, shows the time elapsed, and keeps the recorded trace in place", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByTestId("trace-attempts")).toBeVisible();
    const recordedRows = await card.locator(".trace-panel .trace-panel__list > li").count();

    await card.getByTestId("plan-live").click();
    await expect(card.getByTestId("plan-live")).toBeDisabled();
    const live = card.getByTestId("live-replan");
    await expect(live).toBeVisible();
    await expect(live.getByText(/\d+ s elapsed/)).toBeVisible();
    await expect(live.locator(".trace-panel__event").first()).toBeVisible({ timeout: 5_000 });
    await expect(live.getByTestId("trace-attempts")).toBeVisible({ timeout: 5_000 });

    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 10_000 });
    await expect(card.getByTestId("plan-live")).toBeEnabled();
    await expect(card.locator(".trace-panel .trace-panel__list > li")).toHaveCount(recordedRows);

    // the live panel is gone, but the streamed trace (tool calls, guardrail attempts) stays under the result
    await expect(live).not.toBeVisible();
    const kept = card.getByTestId("live-trace");
    await expect(kept).toBeVisible();
    await expect(kept.locator("> details")).toHaveAttribute("open", "");
    await expect(kept.getByTestId("trace-attempts")).toBeVisible();
    expect(await kept.locator(".trace-panel__event").count()).toBeGreaterThan(0);
    await expect(kept.getByText("propose_play").first()).toBeVisible();

    // the run's play joins the inbox under a "Live run" tag; the recorded play stays selected
    const inbox = page.getByLabel("Play inbox");
    await expect(inbox.locator(".inbox__live")).toHaveCount(1);
    await expect(card.getByTestId("play-ids")).toContainText("play_chips_ds07_v1");
    // ... and selecting it shows that play, which Approve then acts on
    await inbox.locator(".inbox__item").filter({ has: page.locator(".inbox__live") }).click();
    await expect(card.getByTestId("play-ids")).toContainText("play_tea_ds04_v2");
    await expect(card.getByRole("button", { name: "Approve" })).toBeVisible();
  });
});

test.describe("Play Desk: plain language, one figure, honest checks", () => {
  async function openChips(page: import("@playwright/test").Page) {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    return page.getByTestId("play-detail");
  }

  test("the card uses names, and the raw ids sit inside Details", async ({ page }) => {
    const card = await openChips(page);
    await expect(card.getByRole("heading", { name: "Masala Chips 200G" })).toBeVisible();
    await expect(card.getByText("Dark store 7 · Online sell-by breach")).toBeVisible();
    // the demo clock is 12 Sep and the deadline 18 Sep: relative, with the weekday date beside it
    await expect(card.getByTestId("why-now")).toContainText("368 units pass their online sell-by in 6 days (Fri 18 Sep). ₹9,200 is at stake.");
    await expect(card.getByTestId("plan-sentence")).toContainText("Bundle with a popular item.");
    await expect(card.getByTestId("plan-sentence")).toContainText("Offer a bundle of Masala Chips 200G with Coconut Water 1L at ₹61");
    // the inbox also names the store and the mechanic
    await expect(page.getByLabel("Play inbox").getByText("Dark store 7 · Bundle with a popular item").first()).toBeVisible();
    // the technical block is inside the collapsed Details; ids are one click away
    const details = card.getByTestId("card-details");
    await expect(details).not.toHaveAttribute("open", "");
    await details.locator("summary").click();
    await expect(details).toContainText("Household essentials buyers");
    await expect(card.getByTestId("target-ids")).toContainText("SKU-MASALA-CHIPS-200G");
    await expect(card.getByTestId("mechanic-details")).toContainText("bundle");
    await expect(card.getByTestId("segment-ids")).toContainText("seg_5");
  });

  test("guardrails: one summary line, tri-state rows, and no duplicated 'Margin Floor Margin_floor'", async ({ page }) => {
    const card = await openChips(page);
    const section = card.getByTestId("card-checks");
    // mocks/plays.json, chips: 5 checked and held, 2 had nothing to check, 1 waits for the copy
    await expect(section.getByTestId("guardrail-summary")).toHaveText("8 checks: 5 passed, 2 not applicable, 1 pending");
    // nothing failed, so the list is collapsed until asked for
    await expect(section.getByTestId("guardrails-disclosure")).not.toHaveAttribute("open", "");
    await expect(section.locator("li.guardrails__item").first()).toBeHidden();
    await section.getByTestId("guardrail-summary").click();
    const rows = section.locator("li.guardrails__item");
    await expect(rows).toHaveCount(8);
    await expect(rows.filter({ hasText: "Margin floor" }).first()).toContainText("Margin floor");
    await expect(section.getByText("Margin Floor Margin_floor")).toHaveCount(0);
    await expect(section.locator("li[data-state=pass]")).toHaveCount(5);
    await expect(section.locator("li[data-state=not_applicable]")).toHaveCount(2);
    await expect(section.locator("li[data-state=pending]")).toHaveCount(1);
    await expect(section.locator("li[data-state=pending]")).toContainText("Best-before disclosure");
    await expect(section.locator("li[data-state=pending]")).toContainText("(pending)"); // for screen readers
    // every state has an icon (an svg), not just a colour; none of them is read out
    await expect(rows.first().locator("svg[aria-hidden=true]")).toHaveCount(1);

    // the rule id is kept, inside the row's disclosure
    const row = rows.first();
    await row.locator("summary").click();
    await expect(row.locator("code")).toHaveText("margin_floor");
  });

  test("counterfactuals state the canonical figure with its parts, and a near tie is not oversold", async ({ page }) => {
    const card = await openChips(page);
    const figure = card.getByTestId("recovered-figure");
    await expect(card.getByTestId("recovered-figure")).toHaveCount(1); // once on the card, not once per section
    // stub chips: margin 235.14 + waste avoided 541.80 = 776.94
    await expect(figure).toContainText("Recovered vs doing nothing ₹777");
    await expect(figure.getByTestId("recovered-figure-parts")).toContainText("waste avoided (at cost) ₹542 plus margin earned ₹235");
    await expect(card.getByTestId("comparison-line")).toHaveText(
      "Within noise of a blanket 20% markdown, but only this play can be measured against a holdout",
    );
  });

  test("a transfer play's bar no longer counts the avoided waste twice (Tea ends at -₹27,522, ahead of the markdown)", async ({ page }) => {
    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    const card = page.getByTestId("play-detail");
    const bars = card.locator(".counterfactuals");
    await expect(bars.locator(".counterfactuals__row").nth(2).locator(".counterfactuals__value")).toHaveText("-₹27,522");
    await expect(bars.getByTestId("comparison-line")).toHaveText("Beats a blanket 20% markdown by ₹4,493");
    // "This play" is highlighted, and tagged Recommended because it keeps the most of the three
    await expect(bars.locator(".counterfactuals__row--play .counterfactuals__tag")).toHaveText("Recommended");
    await expect(card.getByTestId("recovered-figure")).toContainText("Recovered vs doing nothing ₹7,498");
  });

  test("the holdout slider locks once the play is approved", async ({ page }) => {
    const card = await openChips(page);
    const slider = card.getByLabel("Holdout fraction");
    await expect(slider).toBeEnabled();
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(card.getByTestId("approve-result")).toBeVisible({ timeout: 15_000 });
    await expect(slider).toBeDisabled();
    await expect(card.getByTestId("holdout-locked")).toBeVisible();
    // still locked after looking at another play and coming back
    await page.getByLabel("Play inbox").getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    await expect(page.getByTestId("play-detail").getByLabel("Holdout fraction")).toBeEnabled();
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    await expect(page.getByTestId("play-detail").getByLabel("Holdout fraction")).toBeDisabled();
  });
});
