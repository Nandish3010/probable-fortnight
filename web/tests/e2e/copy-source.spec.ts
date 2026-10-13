import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { copySourceLabel } from "../../lib/approveMachine";
import { FAKE_API, approveSettled, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, openBeat } from "./helpers";

// The badge next to the offer copy after Approve reads copy.source (and copy.provenance) of the /approve
// response and nothing else: "bigquery" -> "Copy: Gemini via BigQuery"; "existing" + provenance
// "bigquery_pregenerated" -> "Copy: written ahead with BigQuery + Gemini"; "existing" alone -> "Copy: stored
// with the play"; "templated" -> "Copy: template"; absent, empty or unknown -> no badge.
// mocks/approve.json carries no copy field (like today's live API), so each case injects it through
// the fake API.

test.describe("copySourceLabel", () => {
  test("only copy.source and copy.provenance decide", () => {
    expect(copySourceLabel({ source: "bigquery" })).toBe("Copy: Gemini via BigQuery");
    expect(copySourceLabel({ source: "bigquery", provenance: "bigquery_pregenerated" })).toBe("Copy: Gemini via BigQuery");
    // live BigQuery copy is the only thing that says "via BigQuery"; stored copy says it was written ahead
    expect(copySourceLabel({ source: "existing", provenance: "bigquery_pregenerated" })).toBe("Copy: written ahead with BigQuery + Gemini");
    expect(copySourceLabel({ source: "existing" })).toBe("Copy: stored with the play");
    expect(copySourceLabel({ source: "existing", provenance: "something-else" })).toBe("Copy: stored with the play");
    expect(copySourceLabel({ source: "templated" })).toBe("Copy: template");
    expect(copySourceLabel({ source: "templated", provenance: "bigquery_pregenerated" })).toBe("Copy: template");
    // never a BigQuery or template claim the field does not make
    expect(copySourceLabel({ source: "something-new" })).toBeNull();
    expect(copySourceLabel({ source: "something-new", provenance: "bigquery_pregenerated" })).toBeNull();
    expect(copySourceLabel({ provenance: "bigquery_pregenerated" })).toBeNull();
    expect(copySourceLabel({ source: "" })).toBeNull();
    expect(copySourceLabel({})).toBeNull();
    expect(copySourceLabel({ source: undefined })).toBeNull();
    expect(copySourceLabel({ source: 3 })).toBeNull();
    expect(copySourceLabel(undefined)).toBeNull();
    expect(copySourceLabel(null)).toBeNull();
  });
});

async function approveWith(page: Page, copy: unknown): Promise<void> {
  await forceLiveApi(page, FAKE_API);
  const body = copy === undefined ? mockFixture("approve") : { ...mockFixture("approve"), copy };
  await fakeApi(page, beatHandlers({ "/approve": okJson(body), "/chat": okJson(mockFixture("chat").greeting) }));
  await openBeat(page);
  await page.getByTestId("approve-button").first().click();
  await approveSettled(page);
}

test.describe("copy-source badge", () => {
  const badge = (page: Page) => page.getByTestId("copy-source");

  test("bigquery: 'Copy: Gemini via BigQuery' with the tooltip", async ({ page }) => {
    await approveWith(page, { source: "bigquery" });
    await expect(badge(page)).toHaveText("Copy: Gemini via BigQuery");
    await expect(badge(page)).toHaveAttribute("title", "Where the offer copy came from");
  });
  test("existing with provenance bigquery_pregenerated: 'Copy: written ahead with BigQuery + Gemini'", async ({ page }) => {
    await approveWith(page, { source: "existing", provenance: "bigquery_pregenerated" });
    await expect(badge(page)).toHaveText("Copy: written ahead with BigQuery + Gemini");
    // the step line says the same, without the prefix, and never calls pre-written copy "generated for this Approve"
    await expect(page.getByTestId("approve-step").nth(0).getByTestId("step-provenance")).toHaveText("written ahead with BigQuery + Gemini");
    await expect(page.getByTestId("approve-result")).not.toContainText(/pre-generated/);
  });
  test("existing alone: 'Copy: stored with the play', no BigQuery claim", async ({ page }) => {
    await approveWith(page, { source: "existing" });
    await expect(badge(page)).toHaveText("Copy: stored with the play");
    await expect(page.getByTestId("approve-result")).not.toContainText(/BigQuery/);
  });
  test("templated: 'Copy: template'", async ({ page }) => {
    await approveWith(page, { source: "templated" });
    await expect(badge(page)).toHaveText("Copy: template");
  });
  test("an unknown source shows no badge: neither BigQuery nor template is claimed", async ({ page }) => {
    await approveWith(page, { source: "gemini-direct" });
    await expect(badge(page)).toHaveCount(0);
    await expect(page.getByTestId("approve-result")).not.toContainText(/Copy:/);
    await approveWith(page, { source: "gemini-direct", provenance: "bigquery_pregenerated" });
    await expect(badge(page)).toHaveCount(0);
  });
  test("the step line stays 'templated' only while the copy source is absent or templated", async ({ page }) => {
    await approveWith(page, { source: "existing", provenance: "bigquery_pregenerated" });
    await expect(page.getByTestId("step-provenance").filter({ hasText: "templated" })).toHaveCount(0);
  });
  test("absent field (today's live API): no badge, and nothing about copy is claimed", async ({ page }) => {
    await approveWith(page, undefined);
    await expect(badge(page)).toHaveCount(0);
    await expect(page.getByTestId("approve-result")).not.toContainText(/BigQuery|Copy:/);
  });
  test("a copy object with no source: no badge", async ({ page }) => {
    await approveWith(page, {});
    await expect(badge(page)).toHaveCount(0);
  });
  test("default mock mode shows no badge (mocks/approve.json has no copy field)", async ({ page }) => {
    await openBeat(page);
    await page.getByTestId("approve-button").first().click();
    await approveSettled(page);
    await expect(badge(page)).toHaveCount(0);
  });

  test("no horizontal overflow at 360 px with the longest label", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await approveWith(page, { source: "bigquery" });
    await expect(badge(page)).toBeVisible();
    await assertNoHorizontalOverflow(page);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`axe: ${scheme}, the result with the badge`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await approveWith(page, { source: "bigquery" });
      await expect(page.getByTestId("meena-text")).toBeVisible({ timeout: 8000 });
      await expect(badge(page)).toBeVisible();
      await page.waitForTimeout(400);
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  }
});
