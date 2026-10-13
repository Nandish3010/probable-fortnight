import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, fakeApi, forceLiveApi, mockFixture, okJson, beatHandlers } from "./helpers";

// The phone view says where the read on screen came from. A staged sample pallet is a REPLAY of a
// recorded Gemini read of an AI-generated photo (agents/capture/vision.py answers it with
// model_id "recorded"); a real upload carries a "Live · Gemini" chip only when the /capture response
// carries a real model id. Pixel 7 project (the file name ends in -phone).

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const REPLAY_TEXT = "REPLAY · sample photo (AI-generated) · recorded Gemini vision read";

// A 1x1 PNG: the upload only needs to be a file the reader can turn into a data URL.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function uploadOwnPhoto(page: Page, modelId: string) {
  await forceLiveApi(page, FAKE_API);
  await fakeApi(page, beatHandlers({ "/capture": okJson({ ...mockFixture("capture"), model_id: modelId, photo_ref: "upload" }) }));
  await page.goto("/phone");
  await page.getByLabel("Own photo (experimental)").setInputFiles({ name: "pallet.png", mimeType: "image/png", buffer: PNG });
  await page.getByTestId("intake-table").waitFor();
}

test.describe("phone view: provenance chip on the read", () => {
  test("a sample photo is labelled REPLAY, with what it replays", async ({ page }) => {
    await page.goto("/phone");
    await expect(page.getByTestId("vision-source")).toHaveCount(0); // nothing read yet, nothing claimed
    await page.getByRole("button", { name: "Pallet 1" }).click();
    const chip = page.getByTestId("vision-source");
    await expect(chip).toBeVisible();
    await expect(chip).toHaveAttribute("data-source", "replay");
    await expect(chip).toHaveText(REPLAY_TEXT);
    await expect(chip).not.toContainText("Live");
    // beside the result table: the chip sits right above it
    const [c, t] = await Promise.all([chip.boundingBox(), page.getByTestId("intake-table").boundingBox()]);
    expect(c!.y + c!.height).toBeLessThanOrEqual(t!.y + 1);
    expect(t!.y - (c!.y + c!.height)).toBeLessThan(40);
  });

  test("a sample whose recorded read is flagged for confirmation is labelled REPLAY too", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 6" }).click();
    await expect(page.getByTestId("vision-source")).toHaveText(REPLAY_TEXT);
  });

  test("the chip goes with the photo: Clear photo removes it", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    await expect(page.getByTestId("vision-source")).toBeVisible();
    await page.getByRole("button", { name: "Clear photo" }).click();
    await expect(page.getByTestId("vision-source")).toHaveCount(0);
  });

  test("an API response marked recorded is a REPLAY, whatever tile it came from", async ({ page }) => {
    await uploadOwnPhoto(page, "recorded");
    await expect(page.getByTestId("vision-source")).toHaveAttribute("data-source", "replay");
  });

  test("an upload read by a real model carries the live chip with the model id", async ({ page }) => {
    await uploadOwnPhoto(page, "gemini-3.5-flash");
    const chip = page.getByTestId("vision-source");
    await expect(chip).toHaveAttribute("data-source", "live");
    await expect(chip).toContainText("Live · Gemini");
    await expect(chip).toContainText("gemini-3.5-flash");
    await expect(chip).not.toContainText("REPLAY");
  });

  test("an upload answered by the stand-in vision is never called live", async ({ page }) => {
    await uploadOwnPhoto(page, "stub-vision");
    const chip = page.getByTestId("vision-source");
    await expect(chip).toHaveAttribute("data-source", "scripted");
    await expect(chip).not.toContainText("Live");
    await expect(chip).not.toContainText("Gemini vision read");
  });
});

test.describe("phone view: provenance chip at 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("the replay chip wraps inside the card and the page does not scroll sideways", async ({ page }) => {
    await page.goto("/phone");
    await page.getByRole("button", { name: "Pallet 1" }).click();
    const chip = page.getByTestId("vision-source");
    await expect(chip).toHaveText(REPLAY_TEXT);
    await assertNoHorizontalOverflow(page);
    const inside = await chip.evaluate((p) => {
      const b = p.querySelector(".badge")!.getBoundingClientRect();
      const card = p.closest(".phone-result")!.getBoundingClientRect();
      return b.left >= card.left - 0.5 && b.right <= card.right + 0.5;
    });
    expect(inside).toBe(true);
  });

  test("the live chip fits too", async ({ page }) => {
    await uploadOwnPhoto(page, "gemini-3.5-flash");
    await expect(page.getByTestId("vision-source")).toContainText("Live · Gemini");
    await assertNoHorizontalOverflow(page);
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`phone view: provenance chip, axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    test("replay chip", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/phone");
      await page.getByRole("button", { name: "Pallet 1" }).click();
      await expect(page.getByTestId("vision-source")).toHaveText(REPLAY_TEXT);
      await page.waitForTimeout(300);
      const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    });

    test("live chip", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await uploadOwnPhoto(page, "gemini-3.5-flash");
      await expect(page.getByTestId("vision-source")).toContainText("Live · Gemini");
      await page.waitForTimeout(300);
      const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  });
}
