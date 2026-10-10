import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { assertNoHorizontalOverflow } from "./helpers";
import { PERSONAS, initialOf, personaForPath, viewAsName } from "../../lib/personas";

// The persona bar (E4): who this screen is for, and "View as" links to the other two screens.
const ROUTES: Array<[string, string, string, string]> = [
  // route, who, role, the two chips
  ["/", "Arjun", "demand planner", "Priya|Meena"],
  ["/desk", "Arjun", "demand planner", "Priya|Meena"],
  ["/outcomes", "Arjun", "demand planner", "Priya|Meena"],
  ["/phone", "Priya", "node manager", "Arjun|Meena"],
  ["/chat", "Meena", "customer", "Priya|Arjun"],
];

const HREF: Record<string, string> = { Priya: "/phone", Arjun: "/", Meena: "/chat" };

test.describe("persona bar: the mapping", () => {
  test("every route on the path has a persona and the others are off it", () => {
    expect(personaForPath("/")?.name).toBe("Arjun");
    expect(personaForPath("/desk/")?.name).toBe("Arjun");
    expect(personaForPath("/phone")?.name).toBe("Priya");
    expect(personaForPath("/chat")?.name).toBe("Meena");
    expect(personaForPath("/feedback")).toBeNull();
    expect(personaForPath(null)).toBeNull();
    expect(PERSONAS.map(viewAsName)).toEqual([
      "View as Priya, node manager",
      "View as Arjun, demand planner",
      "View as Meena, customer",
    ]);
    expect(PERSONAS.map(initialOf)).toEqual(["P", "A", "M"]);
  });
});

test.describe("persona bar: each route", () => {
  for (const [route, who, role, chips] of ROUTES) {
    test(`${route} is for ${who}, ${role}`, async ({ page }) => {
      await page.goto(route);
      const bar = page.getByTestId("persona-bar");
      await expect(bar).toBeVisible();
      await expect(page.getByTestId("persona-who")).toContainText(`This screen is for ${who}, ${role}`);
      // the avatar is an inline SVG, decorative
      const avatar = page.getByTestId("persona-who").locator("svg");
      await expect(avatar).toHaveAttribute("aria-hidden", "true");
      await expect(avatar.locator("text")).toHaveText(who.charAt(0));
      await expect(bar.locator("img")).toHaveCount(0);

      const nav = bar.getByRole("navigation", { name: "View as" });
      const names = chips.split("|");
      await expect(nav.getByRole("link")).toHaveCount(2);
      for (const n of names) {
        const persona = PERSONAS.find((p) => p.name === n)!;
        const link = nav.getByRole("link", { name: viewAsName(persona) });
        await expect(link).toBeVisible();
        await expect(link).toHaveAttribute("href", HREF[n]);
      }
      // the person this screen is already for is not offered
      await expect(nav.getByRole("link", { name: new RegExp(`View as ${who}`) })).toHaveCount(0);
    });
  }

  test("a chip is a plain link: it switches the route, and Back returns", async ({ page }) => {
    await page.goto("/desk");
    await page.getByRole("link", { name: "View as Priya, node manager" }).click();
    await expect(page).toHaveURL(/\/phone$/);
    await expect(page.getByTestId("persona-who")).toContainText("Priya, node manager");
    await page.getByRole("link", { name: "View as Meena, customer" }).click();
    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByTestId("persona-who")).toContainText("Meena, customer");
    await page.goBack();
    await expect(page).toHaveURL(/\/phone$/);
  });

  test("routes off the path have no persona bar", async ({ page }) => {
    await page.goto("/feedback");
    await expect(page.getByTestId("persona-bar")).toHaveCount(0);
  });

  test("chips are 44 px targets on desktop and on a phone", async ({ page }) => {
    for (const vp of [{ width: 1280, height: 800 }, { width: 375, height: 812 }]) {
      await page.setViewportSize(vp);
      await page.goto("/desk");
      for (const link of await page.getByTestId("persona-bar").getByRole("link").all()) {
        const b = (await link.boundingBox())!;
        expect(b.height).toBeGreaterThanOrEqual(44);
      }
    }
  });
});

test.describe("persona bar: small screens", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("under 480 px the role text is hidden but the chips keep their full names", async ({ page }) => {
    await page.goto("/phone");
    await expect(page.getByTestId("persona-who")).toContainText("Priya");
    await expect(page.getByTestId("persona-role")).toBeHidden();
    const chip = page.getByRole("link", { name: "View as Arjun, demand planner" });
    await expect(chip).toBeVisible();
    await expect(chip).toContainText("Arjun");
    await expect(page.getByRole("link", { name: "View as Meena, customer" })).toBeVisible();
  });

  test("from 480 px up the role text shows", async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 800 });
    await page.goto("/phone");
    await expect(page.getByTestId("persona-who")).toContainText("Priya, node manager");
  });
});

test.describe("persona bar: 360 px", () => {
  test.use({ viewport: { width: 360, height: 800 } });
  for (const [route] of ROUTES) {
    test(`${route} does not overflow sideways`, async ({ page }) => {
      await page.goto(route);
      await expect(page.getByTestId("persona-bar")).toBeVisible();
      await assertNoHorizontalOverflow(page);
    });
  }
});

for (const scheme of ["light", "dark"] as const) {
  for (const [name, viewport] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 375, height: 812 }]] as const) {
    test.describe(`persona bar: axe (${scheme}, ${name})`, () => {
      test.use({ viewport, colorScheme: scheme });
      for (const [route] of ROUTES) {
        test(`${route} has no violations`, async ({ page }) => {
          await page.emulateMedia({ reducedMotion: "reduce" });
          await page.goto(route);
          await expect(page.getByTestId("persona-bar")).toBeVisible();
          await page.waitForTimeout(300);
          const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
          expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
        });
      }
    });
  }
}
