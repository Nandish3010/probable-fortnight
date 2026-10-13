import { test, expect } from "@playwright/test";

// De-chrome: neutral STOP, ink numbers, a ruled list instead of cards on the landing, no nested
// panels where nothing is interactive, 44 px targets for what is tapped.

test.describe("de-chrome", () => {
  test("STOP stays neutral on hover and focus: an ink border, never the danger colour", async ({ page }) => {
    await page.goto("/chat");
    const stop = page.getByRole("button", { name: "Customer replies STOP (opt-out demo)" });
    await stop.hover();
    const [border, danger, ink] = await Promise.all([
      stop.evaluate((el) => getComputedStyle(el).borderTopColor),
      page.evaluate(() => {
        const probe = document.createElement("i");
        probe.style.color = "var(--danger)";
        document.body.appendChild(probe);
        const c = getComputedStyle(probe).color;
        probe.remove();
        return c;
      }),
      page.evaluate(() => {
        const probe = document.createElement("i");
        probe.style.color = "var(--accent)";
        document.body.appendChild(probe);
        const c = getComputedStyle(probe).color;
        probe.remove();
        return c;
      }),
    ]);
    await expect.poll(async () => stop.evaluate((el) => getComputedStyle(el).borderTopColor)).not.toBe(danger);
    expect(border).not.toBe(danger);
    expect(ink).not.toBe(danger);
  });

  test("the landing links are a ruled list: three rows, no card-in-card, no shadow", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const rows = page.getByRole("navigation", { name: "Where to go next" }).getByRole("link");
    await expect(rows).toHaveCount(3);
    await expect(page.locator(".card-link, .card-grid")).toHaveCount(0);
    for (let i = 0; i < 3; i++) {
      expect(await rows.nth(i).evaluate((el) => getComputedStyle(el).boxShadow)).toBe("none");
    }
    await expect(rows.nth(0)).toContainText("Play Desk");
    await expect(rows.nth(2)).toContainText("Outcomes");
  });

  test("Outcomes stat numbers are ink, not coloured", async ({ page }) => {
    await page.goto("/outcomes");
    const text = await page.evaluate(() => getComputedStyle(document.body).color);
    const numbers = page.locator(".portfolio-card__number");
    await expect(numbers).toHaveCount(3);
    for (let i = 0; i < 3; i++) {
      expect(await numbers.nth(i).evaluate((el) => getComputedStyle(el).color)).toBe(text);
    }
  });

  test("the decision card figure is ink", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    const [fig, text] = await Promise.all([
      page.getByTestId("recovered-figure-amount").evaluate((el) => getComputedStyle(el).color),
      page.evaluate(() => getComputedStyle(document.body).color),
    ]);
    expect(fig).toBe(text);
  });

  test("the Approve result has no panel inside its panel: the chart and the preview sit on the card", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByTestId("beat-panel").getByRole("button", { name: "Approve" }).click();
    await expect(page.getByTestId("meena-preview")).toBeVisible({ timeout: 30_000 });
    const frame = await page.getByTestId("meena-preview").evaluate((el) => {
      const cs = getComputedStyle(el);
      return { border: cs.borderTopWidth, radius: cs.borderTopLeftRadius };
    });
    expect(frame.border).toBe("0px");
    expect(frame.radius).toBe("0px");
    const wrap = await page.locator("svg.forecast-chart").evaluate((svg) => {
      const cs = getComputedStyle(svg.parentElement!);
      return cs.borderTopWidth;
    });
    expect(wrap).toBe("0px");
  });
});

test.describe("44 px targets on a phone", () => {
  test("the chat page: every visible button, select and link is at least 44 px tall", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click();
    await page.locator(".chat-msg--agent").first().waitFor();
    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>("main button, main select, footer a, main a"))
        .filter((el) => el.getClientRects().length > 0 && getComputedStyle(el).display !== "inline")
        .map((el) => ({ name: (el.textContent || "").trim().slice(0, 30), h: el.getBoundingClientRect().height }))
        .filter((x) => x.h < 43.5),
    );
    expect(small).toEqual([]);
  });

  test("the landing footer links and Reset are 44 px tall targets", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    for (const name of ["Deck", "Repo", "Practitioner feedback"]) {
      const h = await page.getByRole("link", { name, exact: true }).evaluate((el) => el.getBoundingClientRect().height);
      expect(h, name).toBeGreaterThanOrEqual(43.5);
    }
    const reset = await page.getByRole("button", { name: "Reset demo data" }).evaluate((el) => el.getBoundingClientRect().height);
    expect(reset).toBeGreaterThanOrEqual(43.5);
  });
});
