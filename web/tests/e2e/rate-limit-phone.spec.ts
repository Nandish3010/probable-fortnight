import { test, expect } from "@playwright/test";
import { FAKE_API, assertNoHorizontalOverflow, beatHandlers, fakeApi, forceLiveApi, mockFixture, okJson, type FakeHandler } from "./helpers";

// 429 on the phone view's own-photo upload (Pixel 7). The API limits only an uploaded photo (the one
// that reaches Gemini); a sample pallet replays a recorded read and is never limited, so the sample
// still works while the upload is waiting out its cap.

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const SHARED_DETAIL = "demo capacity: the shared limit of 60 capture calls per 15 minutes is reached; try again in about 2 seconds";
const CORS_ORIGIN = `http://localhost:${process.env.PORT || 3100}`;

test("upload: the shared-cap card counts down and unlocks; a sample pallet works meanwhile", async ({ page }) => {
  await forceLiveApi(page, FAKE_API);
  let uploads = 0;
  const capture: FakeHandler = async (route) => {
    const body = route.request().postDataJSON() as { image_data_url?: string };
    if (body.image_data_url) {
      uploads += 1;
      await route.fulfill({
        status: 429,
        headers: {
          "access-control-allow-origin": CORS_ORIGIN,
          "access-control-allow-credentials": "true",
          "access-control-expose-headers": "retry-after",
          "retry-after": "2",
        },
        contentType: "application/json",
        body: JSON.stringify({ detail: SHARED_DETAIL }),
      });
      return;
    }
    await okJson({ ...mockFixture("capture"), model_id: "recorded" })(route);
  };
  await fakeApi(page, beatHandlers({ "/capture": capture }));
  await page.goto("/phone");
  await page.getByLabel("Own photo (experimental)").setInputFiles({ name: "pallet.png", mimeType: "image/png", buffer: PNG });

  const card = page.getByTestId("error-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveAttribute("data-error-kind", "rate_limited");
  await expect(card).toContainText("The demo is busy right now (shared usage limit). Please wait about 2 seconds and try again.");
  const retry = card.getByRole("button", { name: /Retry/ });
  await expect(retry).toBeDisabled();
  await expect(retry).toHaveText(/^Retry in [1-2] s$/);
  await assertNoHorizontalOverflow(page);

  // the sample replays are not part of the cap
  await page.getByRole("button", { name: "Pallet 1" }).click();
  await expect(page.getByTestId("intake-table")).toBeVisible();
  await expect(page.getByTestId("error-card")).toHaveCount(0);
  expect(uploads).toBe(1);
});
