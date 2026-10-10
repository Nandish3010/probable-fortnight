import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";

// The phone view (/phone) on a phone: a tap on a sample tile brings the result into view and puts
// focus on it, thumbnails load behind skeletons, the table reads Product / Best before / Packs /
// Confidence with names and flagged low confidence, the mic stub explains itself, and the fallback
// gap is labelled. Pixel 7 project; the 360 px describes shrink it.

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function capturePallet(page: Page, name: string) {
  await page.goto("/phone");
  await page.getByRole("button", { name }).click();
  await page.getByTestId("intake-table").waitFor();
}

test.describe("phone view: before a photo", () => {
  test("the intro says capture to gap", async ({ page }) => {
    await page.goto("/phone");
    await expect(page.getByText("Capture to gap: photograph a pallet, confirm what Taal read, and see the gap it finds.")).toBeVisible();
  });

  test("the mic stub is disabled and says why, in words on the screen (no unexplained greyed icon)", async ({ page }) => {
    await page.goto("/phone");
    const mic = page.getByRole("button", { name: "Voice input (not available)" });
    await expect(mic).toBeDisabled();
    await expect(mic).toHaveAttribute("title", "Voice is not part of this demo");
    await expect(mic).toHaveAccessibleDescription("Voice is not part of this demo");
    await expect(page.getByText("Voice is not part of this demo", { exact: true })).toBeVisible();
  });

  test("thumbnails sit on a placeholder of their own size while the image loads", async ({ page }) => {
    await page.route("**/_next/image**", async (route) => {
      await new Promise((r) => setTimeout(r, 2500));
      await route.continue();
    });
    await page.goto("/phone");
    const frames = page.locator(".photo-choice__frame");
    await expect(frames).toHaveCount(7);
    const first = frames.first();
    await expect(first.getByTestId("skeleton")).toBeVisible();
    const box = (await first.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(80);
    expect(Math.abs(box.height - box.width)).toBeLessThan(2); // a square tile, not a collapsed one
    const bg = await first.getByTestId("skeleton").evaluate((el) => getComputedStyle(el).backgroundImage);
    expect(bg).toContain("gradient"); // a shimmer, not a blank square
    const loaded = await first.locator("img").evaluate((img) => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0);
    expect(loaded).toBe(false); // it really was still loading
    // and the tile fills in afterwards
    await expect.poll(() => first.locator("img").evaluate((img) => (img as HTMLImageElement).naturalWidth), { timeout: 10_000 }).toBeGreaterThan(0);
  });
});

test.describe("phone view: a tap on a sample tile", () => {
  test("scrolls the result into view and moves focus to it", async ({ page }) => {
    await page.goto("/phone");
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await page.getByRole("button", { name: "Pallet 1" }).click();
    const result = page.getByTestId("phone-result");
    await expect(result).toBeVisible();
    await expect(result).toBeFocused();
    await expect(result).toHaveAccessibleName("Photo result");
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(50);
    await expect.poll(async () => (await result.boundingBox())!.y).toBeLessThan(160);
    expect((await result.boundingBox())!.y).toBeGreaterThanOrEqual(0);
    // while the pallet is read the placeholder says so; then the table arrives in the same region
    await expect(page.getByTestId("intake-table")).toBeVisible();
    await expect(result.getByTestId("intake-table")).toBeVisible();
  });

  test("a second tap on another tile brings the new result into view again", async ({ page }) => {
    await capturePallet(page, "Pallet 1");
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.getByRole("button", { name: "Pallet 6" }).click();
    await expect(page.getByTestId("phone-result")).toBeFocused();
    await expect.poll(async () => (await page.getByTestId("phone-result").boundingBox())!.y).toBeLessThan(160);
  });
});

test.describe("phone view: the table", () => {
  test("headers are Product, Best before, Packs and Confidence, and none is cut mid-word", async ({ page }) => {
    await capturePallet(page, "Pallet 1");
    const headers = page.getByTestId("intake-table").locator("th");
    await expect(headers).toHaveText(["Product", "Best before", "Packs", "Confidence"]);
    const clipped = await headers.evaluateAll((ths) =>
      ths
        .map((th) => {
          const range = document.createRange();
          range.selectNodeContents(th);
          const words = (th.textContent ?? "").split(" ");
          // each word must fit in the cell on one line: the widest word is no wider than the content box
          const cs = getComputedStyle(th);
          const inner = th.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          const widest = Math.max(
            ...words.map((w) => {
              const probe = document.createElement("span");
              probe.style.cssText = "position:absolute;visibility:hidden;white-space:nowrap;font:inherit;letter-spacing:inherit";
              probe.textContent = w;
              th.appendChild(probe);
              const width = probe.getBoundingClientRect().width;
              probe.remove();
              return width;
            }),
          );
          return { text: th.textContent, widest, inner, scroll: th.scrollWidth, client: th.clientWidth };
        })
        .filter((h) => h.widest > h.inner + 0.5 || h.scroll > h.client + 0.5),
    );
    expect(clipped, JSON.stringify(clipped)).toEqual([]);
  });

  test("product names come from the label map; the raw id is behind the id disclosure", async ({ page }) => {
    await capturePallet(page, "Pallet 1");
    const row = page.getByTestId("intake-table").locator("tbody tr").first();
    await expect(row).toContainText("Masala Chips 200G");
    await expect(row.locator("details")).not.toHaveAttribute("open", "");
    await row.locator("summary").click();
    await expect(row).toContainText("SKU-MASALA-CHIPS-200G");
  });

  test("a confidence under 80% is flagged in the warning colour, with an icon and text; the rest are not", async ({ page }) => {
    await capturePallet(page, "Pallet 6");
    // Pallet 6 reads: Wheat Atta sku 80 / date 70 / count 90 and Poha sku 75 / date 65 / count 85
    const low = page.getByTestId("intake-table").locator(".conf--low");
    await expect(low).toHaveCount(3);
    await expect(low).toContainText(["date 70%", "sku 75%", "date 65%"]);
    await expect(low.locator('[data-icon="alert-triangle"]')).toHaveCount(3);
    await expect(low.locator(".visually-hidden")).toHaveText(["(low)", "(low)", "(low)"]);
    await expect(page.getByTestId("intake-table").locator(".conf:not(.conf--low)")).toContainText(["sku 80%", "count 90%", "count 85%"]);
    const colours = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.style.color = "var(--warn-text)";
      document.body.appendChild(probe);
      const warn = getComputedStyle(probe).color;
      probe.remove();
      const cells = Array.from(document.querySelectorAll<HTMLElement>(".intake-table .conf"));
      return {
        warn,
        low: cells.filter((c) => c.dataset.low === "true").map((c) => getComputedStyle(c).color),
        ok: cells.filter((c) => c.dataset.low !== "true").map((c) => getComputedStyle(c).color),
      };
    });
    expect(colours.low).toEqual([colours.warn, colours.warn, colours.warn]);
    expect(colours.ok.length).toBeGreaterThan(0);
    for (const c of colours.ok) expect(c).not.toBe(colours.warn);
    // every high-confidence value is still printed as text
  });

  test("the Confirm button is the primary button, and the gating is unchanged", async ({ page }) => {
    await capturePallet(page, "Pallet 6");
    const confirm = page.getByRole("button", { name: "Confirm rows" });
    await expect(confirm).toHaveClass(/button-primary/);
    await expect(confirm).toBeDisabled();
    const fill = await confirm.evaluate((el) => getComputedStyle(el).backgroundColor);
    const accent = await page.evaluate(() => {
      const probe = document.createElement("span");
      probe.style.backgroundColor = "var(--accent)";
      document.body.appendChild(probe);
      const c = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return c;
    });
    expect(fill).not.toBe(accent); // disabled: muted
    await page.getByTestId("intake-table").locator(".confirm-row").getByRole("button", { name: "Yes" }).click();
    await expect(confirm).toBeEnabled();
    expect(await confirm.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe(accent);
    expect((await confirm.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  });
});

test.describe("phone view: the gap after Confirm", () => {
  test("no photographed item at risk: a clear result card, and the node's biggest gap only behind a button", async ({ page }) => {
    await capturePallet(page, "Pallet 6");
    await page.getByTestId("intake-table").locator(".confirm-row").getByRole("button", { name: "Yes" }).click();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    const card = page.getByTestId("phone-no-risk");
    await expect(card.getByRole("heading", { name: "No sell-by risk for these items" })).toBeFocused();
    await expect(card).toContainText("Nothing you photographed is close to its online sell-by date, so Taal has no play to propose.");
    // no unrelated gap or number until it is asked for
    await expect(page.getByTestId("why-now")).toHaveCount(0);
    await expect(page.getByText("Fallback gap", { exact: true })).toHaveCount(0);
    await expect(page.getByTestId("gap-fallback-note")).toHaveCount(0);
    await card.getByRole("button", { name: "See the node's biggest open gap" }).click();
    await expect(page.getByText("Fallback gap", { exact: true })).toBeVisible();
    await expect(page.getByTestId("gap-fallback-note")).toHaveText(
      "None of the photographed items raised a gap. Showing the node's biggest open gap instead.",
    );
    await expect(card.getByRole("button", { name: "See the node's biggest open gap" })).toHaveCount(0);
    // the Spot step was recorded when the rows were confirmed
    const spot = await page.evaluate(() =>
      Object.keys(localStorage).filter((k) => k.startsWith("taal_progress:")).map((k) => JSON.parse(localStorage.getItem(k) ?? "{}").spot),
    );
    expect(spot).toContain(true);
  });

  test("a gap from the photo carries no fallback label", async ({ page }) => {
    await capturePallet(page, "Pallet 1");
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await expect(page.getByTestId("why-now")).toBeVisible();
    await expect(page.getByText("Fallback gap", { exact: true })).toHaveCount(0);
  });
});

test.describe("phone view: no horizontal overflow at 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });

  test("before, while reading, after capture with a flagged row, after Confirm with a fallback gap, after Approve", async ({ page }) => {
    await page.goto("/phone");
    await assertNoHorizontalOverflow(page);
    await page.getByRole("button", { name: "Pallet 6" }).click();
    await page.getByText("Reading pallet…").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByTestId("intake-table").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByTestId("intake-table").locator(".confirm-row").getByRole("button", { name: "Yes" }).click();
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await page.getByTestId("phone-no-risk").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByRole("button", { name: "See the node's biggest open gap" }).click();
    await page.getByTestId("gap-fallback-note").waitFor();
    await assertNoHorizontalOverflow(page);
  });

  test("after Confirm with a gap from the photo, and after Approve", async ({ page }) => {
    await capturePallet(page, "Pallet 1");
    await page.getByRole("button", { name: "Confirm rows" }).click();
    await page.getByTestId("why-now").waitFor();
    await assertNoHorizontalOverflow(page);
    await page.getByRole("button", { name: "Approve" }).click();
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 30_000 });
    await assertNoHorizontalOverflow(page);
  });

  test("the table headers still fit at 360 px", async ({ page }) => {
    await capturePallet(page, "Pallet 1");
    const clipped = await page.getByTestId("intake-table").locator("th").evaluateAll((ths) =>
      ths.filter((th) => th.scrollWidth > th.clientWidth + 0.5).map((th) => th.textContent),
    );
    expect(clipped).toEqual([]);
  });
});

for (const scheme of ["light", "dark"] as const) {
  test.describe(`phone view: axe, ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    test("before a photo, after capture with a flagged row, after Confirm", async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/phone");
      await page.waitForTimeout(300);
      let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "before: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
      await page.getByRole("button", { name: "Pallet 6" }).click();
      await page.getByTestId("intake-table").waitFor();
      await page.waitForTimeout(300);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "captured: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
      await page.getByTestId("intake-table").locator(".confirm-row").getByRole("button", { name: "Yes" }).click();
      await page.getByRole("button", { name: "Confirm rows" }).click();
      await page.getByTestId("phone-no-risk").waitFor();
      await page.waitForTimeout(300);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "no risk: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
      await page.getByRole("button", { name: "See the node's biggest open gap" }).click();
      await page.getByTestId("gap-fallback-note").waitFor();
      await page.waitForTimeout(300);
      r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      expect(r.violations, "confirmed: " + JSON.stringify(r.violations, null, 2)).toEqual([]);
    });
  });
}
