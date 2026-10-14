import { test, expect, type Page } from "@playwright/test";
import { copySourceLabel, copyStepLine } from "../../lib/approveMachine";
import { PROVENANCE } from "../../lib/planSteps";
import { FAKE_API, approveSettled, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, openBeat } from "./helpers";

// One source of truth for the Approve copy line: the provenance line on the "Writing the offer" step and
// the "Copy: ..." badge on the result both come from copySourceParts() in lib/approveMachine.ts, so they
// cannot contradict each other. While the request is in flight the step makes no claim about the source.

const CASES = [
  { name: "bigquery", copy: { source: "bigquery" }, badge: "Copy: Gemini via BigQuery", step: "Gemini via BigQuery" },
  {
    name: "existing + bigquery_pregenerated",
    copy: { source: "existing", provenance: "bigquery_pregenerated" },
    badge: "Copy: pre-generated and stored",
    step: "pre-generated and stored",
  },
  { name: "existing alone", copy: { source: "existing" }, badge: "Copy: stored with the play", step: "stored with the play" },
  { name: "templated", copy: { source: "templated" }, badge: "Copy: template", step: "templated (BigQuery attempted under a budget)" },
  { name: "unknown source", copy: { source: "something-new" }, badge: null, step: null },
  { name: "absent copy", copy: undefined, badge: null, step: null },
] as const;

test.describe("copy line mapping (one function)", () => {
  for (const c of CASES) {
    test(`${c.name}: step line and badge are derived together`, () => {
      expect(copySourceLabel(c.copy)).toBe(c.badge);
      expect(copyStepLine(c.copy)).toBe(c.step);
      // The step line is the badge without its "Copy: " prefix, except that "template" is spelled out.
      if (c.badge && c.step && c.copy?.source !== "templated") expect(c.badge).toBe(`Copy: ${c.step}`);
    });
  }
  test("only a templated source ever produces the word templated", () => {
    for (const c of CASES) if (c.copy?.source !== "templated") expect(copyStepLine(c.copy) ?? "").not.toMatch(/templated/i);
  });
  test("the in-flight line makes no claim", () => {
    expect(PROVENANCE.offerCopyPending).not.toMatch(/templated|BigQuery|Gemini/i);
  });
});

/** Opens the beat on a fake API whose /approve answer is held back until the returned function is called. */
async function approveHeld(page: Page, copy: unknown): Promise<() => void> {
  await forceLiveApi(page, FAKE_API);
  const body = copy === undefined ? mockFixture("approve") : { ...mockFixture("approve"), copy };
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  await fakeApi(
    page,
    beatHandlers({
      "/approve": async (route) => {
        await gate;
        await okJson(body)(route);
      },
      "/chat": okJson(mockFixture("chat").greeting),
    }),
  );
  await openBeat(page);
  await page.getByTestId("approve-button").first().click();
  return release;
}

test.describe("Approve: step line agrees with the badge", () => {
  const stepLine = (page: Page) => page.getByTestId("approve-step").nth(0).getByTestId("step-provenance");

  test("in flight the copy step says nothing about the source (no 'templated', no 'BigQuery')", async ({ page }) => {
    const release = await approveHeld(page, { source: "bigquery" });
    await expect(page.getByTestId("approve-step")).toHaveCount(3);
    await expect(stepLine(page)).toHaveText(PROVENANCE.offerCopyPending);
    const text = await page.getByTestId("approve-steps").innerText();
    expect(text).not.toMatch(/templated/i);
    expect(text).not.toMatch(/BigQuery/i);
    release();
    await approveSettled(page);
  });

  for (const c of CASES) {
    test(`${c.name}: after the response the step line and the badge agree`, async ({ page }) => {
      const release = await approveHeld(page, c.copy);
      await expect(stepLine(page)).toHaveText(PROVENANCE.offerCopyPending);
      release();
      await approveSettled(page);
      const badge = page.getByTestId("copy-source");
      if (c.badge === null) {
        await expect(badge).toHaveCount(0);
        await expect(stepLine(page)).toHaveCount(0);
      } else {
        await expect(badge).toHaveText(c.badge);
        await expect(stepLine(page)).toHaveText(c.step);
        if (c.copy?.source !== "templated") {
          await expect(page.getByTestId("approve-steps")).not.toContainText(/templated/i);
        }
      }
    });
  }
});
