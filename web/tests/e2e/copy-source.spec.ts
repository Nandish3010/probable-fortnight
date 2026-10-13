import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { copySourceLabel } from "../../lib/approveMachine";
import { FAKE_API, approveSettled, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, openBeat } from "./helpers";

// The badge next to the offer copy after Approve reads copy.source of the /approve response and nothing
// else: "bigquery" -> "Copy: Gemini via BigQuery", any other string -> "Copy: template", absent -> no badge.
// mocks/approve.json carries no copy field (like today's live API), so each case injects it through
// the fake API.

test.describe("copySourceLabel", () => {
  test("only copy.source decides", () => {
    expect(copySourceLabel({ source: "bigquery" })).toBe("Copy: Gemini via BigQuery");
    expect(copySourceLabel({ source: "templated" })).toBe("Copy: template");
    expect(copySourceLabel({ source: "existing" })).toBe("Copy: template");
    expect(copySourceLabel({ source: "something-new" })).toBe("Copy: template");
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
  test("templated: 'Copy: template'", async ({ page }) => {
    await approveWith(page, { source: "templated" });
    await expect(badge(page)).toHaveText("Copy: template");
  });
  test("existing, and a value the UI has not seen, also read 'Copy: template'", async ({ page }) => {
    await approveWith(page, { source: "existing" });
    await expect(badge(page)).toHaveText("Copy: template");
  });
  test("an unknown value reads 'Copy: template', never a model claim", async ({ page }) => {
    await approveWith(page, { source: "gemini-direct" });
    await expect(badge(page)).toHaveText("Copy: template");
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
