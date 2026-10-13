import { test, expect } from "@playwright/test";
import { API, asVisitor, collectConsoleErrors, expectNoConsoleErrors, visitorHeaders } from "./helpers";

// Provenance badges (Badge.tsx / SourceBadge.tsx) against the real stack, stub backend. As of
// 2026-09-28 a real, committed Gemini recording exists for the flagship gap
// (eval/raw/planner_real_traces_2026-09-28/, harness/record_flagship_traces.py + 5 independent
// real Vertex runs), and harness/seed_plays.py seeds it regardless of TAAL_MODEL_BACKEND -- so
// the flagship's own trace is genuinely "recorded_gemini" here, checked with no injection at all.
// The hero Tea gap (gap_tea_ds04) also became a committed Gemini recording, so it has its own
// "Recorded from Gemini" assertion. A still-scripted demo gap (gap_quinoa_out02 -- no recording has
// been made for it) proves the "Scripted fixture" branch still works, also with no injection. The remaining two PlanSource
// values (live_gemini, deterministic_rules) cannot occur for real in this environment (no Vertex
// credentials, and the stub backend basically never misses its deadline), so those two tests
// inject a response with page.route to exercise each badge's UI branch. Every injected value below
// is clearly fabricated (fake run ids, a round elapsed_ms, an invented fallback reason) -- never a
// real measurement or a real recording.
test.describe("Play Desk: provenance badges (real stack, stub backend)", () => {
  test("the real flagship trace badge reads Recorded from Gemini · <date>", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-flagship");
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByText(/Recorded from Gemini · \d{1,2} \S+ 2026/)).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test("a scripted play (gap_quinoa_out02, never recorded) still reads Scripted fixture", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-scripted");
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Quinoa 500G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByText("Scripted fixture")).toBeVisible();
    // A scripted fixture shows its badge alone: no model chip, no model id anywhere in the header.
    await expect(card.locator(".trace-panel").getByTestId("model-chip")).toHaveCount(0);
    await expect(card.locator(".trace-panel__header")).not.toContainText(/gemini-/);
    await expectNoConsoleErrors(errors);
  });

  test("the hero Tea play now reads Recorded from Gemini · <date>", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-tea");
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Darjeeling Tea 100G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByText(/Recorded from Gemini · \d{1,2} \S+ 2026/)).toBeVisible();
    await expect(card.locator(".trace-panel").getByText("Scripted fixture")).not.toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test("Live · Gemini for a re-plan done payload with source live_gemini (injected fixture)", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-live-gemini");

    // INJECTED FIXTURE, not real data: this container has no Vertex credentials, so POST /rerun
    // never actually resolves with source "live_gemini" here (services/api/main.py runs the real
    // stub-backend planner underneath this same request). Fabricated to exercise the "Re-plan
    // result" section's "live-gemini" SourceBadge branch; status "no_play" is a genuine real-world
    // shape for this source (agents/planner/run.py's resolve_source: a live model call can still
    // end in no_play).
    await page.route("**/events/*/stream", async (route) => {
      const done = {
        run_id: "run_injected_live", status: "no_play", policy_version: "v2",
        iterations: 3, elapsed_ms: 31200, source: "live_gemini", planner_source: "model", fallback_reason: null,
      };
      await route.fulfill({ contentType: "text/event-stream", body: `event: done\ndata: ${JSON.stringify(done)}\n\n` });
    });

    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    const policy = card.locator("textarea").last();
    await policy.fill(await policy.inputValue());
    await card.getByRole("button", { name: /Change policy/ }).click();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 20_000 });
    await expect(card.getByText("Live · Gemini")).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test("Plan live three times: every result carries the model chip, naming the model that authored the run (injected stream)", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    const vid = "live-desk-sources-chip-x3";
    await asVisitor(page, vid);

    // INJECTED FIXTURE, not real data: no Vertex credentials here, so each run's stream is fabricated
    // as a Gemini-authored run (source live_gemini, run_summary.model gemini-3.5-flash) with a distinct
    // run time, carrying the real chips play from the API as its result. /health is made to name a
    // DIFFERENT model today, to prove the chip names the model that wrote the run, not today's config.
    const plays = (await (await page.request.get(`${API}/plays`, { headers: visitorHeaders(vid) })).json()) as { gap_id: string }[];
    const play = plays.find((p) => p.gap_id === "gap_chips_ds07");
    expect(play).toBeTruthy();
    // React's dev double mount may open a run's stream twice; the run number, not the stream count, sets the run time.
    let streams = 0;
    let runNo = 0;
    await page.route("**/events/*/stream", async (route) => {
      streams += 1;
      const elapsed = 30_000 + runNo * 1000;
      const runId = `run_injected_chip_${runNo}`;
      const record = { seq: 1, run_id: runId, invocation_id: "", author: "planner_run", timestamp: "2026-10-12T00:00:00Z", ts_offset_ms: 100, level: "info", text: "Planner started (injected)" };
      const summary = { ...record, seq: 2, kind: "run_summary", ts_offset_ms: elapsed, source: "live_gemini", status: "proposed", model: "gemini-3.5-flash", backend: "vertex", elapsed_ms: elapsed, text: "Run finished (injected)" };
      const done = { run_id: runId, status: "proposed", policy_version: "v2", iterations: 1, elapsed_ms: elapsed, source: "live_gemini", planner_source: "model", fallback_reason: null, play: { ...play, play_id: `play_chips_ds07_v2_injected_${runNo}`, trace_ref: `events/${runId}` } };
      const body = `data: ${JSON.stringify(record)}\n\ndata: ${JSON.stringify(summary)}\n\nevent: done\ndata: ${JSON.stringify(done)}\n\n`;
      await route.fulfill({ contentType: "text/event-stream", body });
    });
    await page.route("**/health", async (route) => {
      const res = await route.fetch();
      const h = await res.json();
      await route.fulfill({ response: res, json: { ...h, model: "gemini-9-future" } });
    });

    await page.goto("/desk");
    await page.getByLabel("Play inbox").getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    for (let run = 1; run <= 3; run += 1) {
      runNo = run;
      const accepted = page.waitForResponse((r) => r.url().endsWith("/rerun") && r.request().method() === "POST");
      await card.getByTestId("plan-live").click();
      const body = (await (await accepted).json()) as { status_url: string };
      // the stub run behind the injected stream must finish before the next POST, or it answers 409
      for (let i = 0; i < 40; i += 1) {
        const st = (await (await page.request.get(`${API}${body.status_url}`, { headers: visitorHeaders(vid) })).json()) as { status: string };
        if (st.status !== "running") break;
        await page.waitForTimeout(500);
      }
      await expect(card.getByTestId("rerun-effort")).toBeVisible({ timeout: 20_000 });
      const chip = card.getByRole("heading", { name: "Re-plan result" }).locator("xpath=..").getByTestId("model-chip");
      await expect(chip).toHaveCount(1);
      await expect(chip).toHaveAttribute("data-model", "gemini-3.5-flash");
      await expect(chip).toHaveText(`gemini-3.5-flash · ${(30 + run).toFixed(1)} s`);
      await expect(card.getByRole("button", { name: "Plan live" })).toBeEnabled({ timeout: 10_000 });
    }
    expect(streams).toBeGreaterThanOrEqual(3);
    await expectNoConsoleErrors(errors);
  });

  test("Rules (fallback) with its reason for a re-plan done payload with source deterministic_rules (injected fixture)", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-rules");

    // INJECTED FIXTURE, not real data: the stub backend basically never misses its deadline, so
    // POST /rerun never actually resolves with source "deterministic_rules" here. Fabricated to
    // exercise the "Re-plan result" section's "rules" SourceBadge branch and its fallback reason.
    await page.route("**/events/*/stream", async (route) => {
      const done = {
        run_id: "run_injected_rules", status: "no_play", policy_version: "v2", iterations: 5, elapsed_ms: 45210,
        source: "deterministic_rules", planner_source: "deterministic_fallback",
        fallback_reason: "deadline exceeded after 45s",
      };
      await route.fulfill({ contentType: "text/event-stream", body: `event: done\ndata: ${JSON.stringify(done)}\n\n` });
    });

    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    const policy = card.locator("textarea").last();
    await policy.fill(await policy.inputValue());
    await card.getByRole("button", { name: /Change policy/ }).click();
    await expect(card.getByRole("heading", { name: "Re-plan result" })).toBeVisible({ timeout: 20_000 });
    await expect(card.getByText("Rules (fallback)")).toBeVisible();
    // The reason appears twice (the plain-English message and the badge detail); either is enough.
    await expect(card.getByText(/deadline exceeded after 45s/).first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });
});

// One gap count: the Desk lists the current scan and Outcomes reads the portfolio summary
// (mocks/portfolio_summary.json, written by python -m jobs.portfolio). They must agree.
test.describe("Desk and Outcomes agree on the gap count (real stack)", () => {
  test("the Desk heading and the Outcomes portfolio card both say the same number of gaps", async ({ page }) => {
    await asVisitor(page, "live-gap-count");
    await page.goto("/desk");
    const heading = page.getByTestId("inbox-heading");
    await expect(heading).toHaveText(/^Top [1-9]\d* of [\d,]+ gaps/);
    const desk = (await heading.innerText()).match(/of ([\d,]+) gaps/)![1];
    await page.goto("/outcomes");
    await expect(page.getByTestId("portfolio-gap-count")).toHaveText(`across ${desk} gaps`);
  });
});
