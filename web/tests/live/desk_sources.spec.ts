import { test, expect } from "@playwright/test";
import { asVisitor, collectConsoleErrors, expectNoConsoleErrors } from "./helpers";

// Provenance badges (Badge.tsx / SourceBadge.tsx) against the real stack, stub backend. Today no
// real Gemini recording is committed (harness/recorded_traces.py finds none), so the flagship's
// own trace is genuinely "scripted_stub" -- checked here with no injection at all. The other three
// PlanSource values (recorded_gemini, live_gemini, deterministic_rules) cannot occur for real in
// this environment (no recording, no Vertex credentials, and the stub backend basically never
// misses its deadline), so those three tests inject a response with page.route to exercise each
// badge's UI branch. Every injected value below is clearly fabricated (fake run ids, a round
// elapsed_ms, an invented fallback reason) -- never a real measurement or a real recording.
test.describe("Play Desk: provenance badges (real stack, stub backend)", () => {
  test("the real flagship trace badge reads Scripted fixture", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-flagship");
    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByText("Scripted fixture")).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test("Recorded from Gemini · <date> for a trace whose events response carries source recorded_gemini (injected fixture)", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-desk-sources-recorded");

    // INJECTED FIXTURE, not real data: no committed recording exists in this repo, so GET
    // /events/{run_id} never actually returns source "recorded_gemini" here. Fabricated to
    // exercise TracePanel's "recorded" SourceBadge branch. Matches "**/events/*" only (one path
    // segment), so the separate "/events/{run_id}/stream" route below is unaffected.
    await page.route("**/events/*", async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          run_id: "run_injected_recorded",
          recorded_at: "2026-09-20T10:00:00Z",
          source: "recorded_gemini",
          events: [
            { seq: 0, run_id: "run_injected_recorded", invocation_id: "", author: "planner", timestamp: 1758361200, ts_offset_ms: 0, level: "info", text: "Plan gap_chips_ds07" },
            {
              seq: 1, run_id: "run_injected_recorded", invocation_id: "", author: "planner_run", kind: "run_summary",
              timestamp: 1758361201, ts_offset_ms: 1000, level: "ok", source: "recorded_gemini", status: "proposed",
              fallback_reason: null, recorded_at: "2026-09-20T10:00:00Z",
              text: "Run finished: play proposed (recorded_gemini) in 1.0 s",
            },
          ],
        }),
      });
    });

    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");
    await expect(card.locator(".trace-panel").getByText(/Recorded from Gemini · \d{1,2} \S+ 2026/)).toBeVisible();
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
