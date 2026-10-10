import { test, expect } from "@playwright/test";
import { asVisitor, collectConsoleErrors, expectNoConsoleErrors } from "./helpers";

// ApprovePanel.tsx's failure note used to repeat "(live call failed)" twice in one sentence, and
// lived inside the branch that only renders once `result` is set -- so a genuine POST /approve
// failure (`result` never gets set) could never actually show it. It is now an ErrorCard
// ("Something went wrong" for a 500) with a Retry button. lib/api.ts's approve() only
// reaches the network at all outside mock mode, so this can only be exercised against the real
// stack (`make live-test`), never the e2e mock suite.
//
// Injecting the 500 makes Chromium itself log "Failed to load resource: the server responded
// with a status of 500" to the console -- expected noise from this test's own fault injection,
// not a defect. Only that one message is dropped below, locally to this test (helpers.ts's
// shared expectNoConsoleErrors is untouched), so any other console error -- a real regression --
// still fails the test.
const EXPECTED_INJECTED_500 = /Failed to load resource.*500/i;

test.describe("Approve: a failed live call surfaces its message exactly once", () => {
  test("500 from POST /approve shows the failure note once and leaves the button for a retry", async ({ page }) => {
    const errors = collectConsoleErrors(page);
    await asVisitor(page, "live-approve-failure");

    // INJECTED FAILURE, not a real backend fault: fulfil the real POST /approve with a 500 so
    // ApprovePanel's catch branch runs. The request never reaches services/api/main.py.
    let intercepted = 0;
    await page.route("**/approve", async (route) => {
      intercepted += 1;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "injected failure (web/tests/live/approve_failure.spec.ts)" }),
      });
    });

    await page.goto("/desk");
    const inbox = page.getByLabel("Play inbox");
    await inbox.getByRole("button", { name: /Masala Chips 200G/ }).first().click();
    const card = page.getByTestId("play-detail");

    await card.getByRole("button", { name: "Approve" }).click();
    const error = card.getByTestId("approve-error");
    await expect(error).toBeVisible({ timeout: 15_000 });
    expect(intercepted).toBeGreaterThan(0);

    // Stated once: the bug this guards against repeated the failure twice in one sentence.
    const text = await error.innerText();
    expect(text.match(/something went wrong/gi)?.length ?? 0).toBe(1);
    expect(text).not.toMatch(/live call failed/i);
    await expect(card.getByTestId("approve-error")).toHaveCount(1);

    // The call genuinely failed -- no result panel ever appeared alongside the failure note.
    await expect(card.getByTestId("approve-result")).toHaveCount(0);

    // The button is still there, and the card offers Retry: a judge can retry once the injected failure is gone.
    await expect(card.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(error.getByRole("button", { name: "Retry" })).toBeVisible();

    // Any console error other than our own injected 500 is still a real defect.
    await expectNoConsoleErrors(errors.filter((e) => !EXPECTED_INJECTED_500.test(e)));
  });
});
