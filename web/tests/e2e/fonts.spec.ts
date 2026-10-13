import { test, expect } from "@playwright/test";

// app/layout.tsx self-hosts IBM Plex Sans, IBM Plex Mono and Noto Sans Kannada with next/font/local
// (files in app/fonts). next/font/local generates its own family names (like '__plexSans_a1b2c3'),
// so these tests read the family names back from the --font-sans / --font-mono tokens instead of
// matching a literal "IBM Plex". The tokens list the generated families first, then the system stack.
const SYSTEM = /^(-apple-system|BlinkMacSystemFont|system-ui|Segoe UI|Roboto|Helvetica|Arial|sans-serif|ui-monospace|SFMono-Regular|Menlo|Consolas|monospace)$/i;

const families = (token: string) => token.split(",").map((s) => s.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);

test.describe("fonts", () => {
  test("--font-sans and --font-mono start with the self-hosted faces, ahead of the system stack", async ({ page }) => {
    await page.goto("/");
    const tokens = await page.evaluate(() => {
      const cs = getComputedStyle(document.documentElement);
      return {
        sans: cs.getPropertyValue("--font-sans").trim(),
        mono: cs.getPropertyValue("--font-mono").trim(),
        bodyFamily: getComputedStyle(document.body).fontFamily,
      };
    });
    const sans = families(tokens.sans);
    const mono = families(tokens.mono);
    // [plexSans, plexSans Fallback, notoKannada, notoKannada Fallback, ...system stack]; [plexMono, plexMono Fallback, ...system stack]
    const firstSystem = (list: string[]) => list.findIndex((f) => SYSTEM.test(f));
    expect(sans[0], tokens.sans).not.toMatch(SYSTEM);
    const kannada = sans.findIndex((f) => /kannada/i.test(f) && !/fallback/i.test(f));
    expect(kannada, tokens.sans).toBeGreaterThan(0);
    expect(firstSystem(sans), tokens.sans).toBeGreaterThan(kannada);
    expect(mono[0], tokens.mono).not.toMatch(SYSTEM);
    expect(firstSystem(mono), tokens.mono).toBeGreaterThan(0);
    // the page really uses the first family, and it is not the system stack
    expect(families(tokens.bodyFamily)[0]).toBe(sans[0]);
    test.info().annotations.push({ type: "--font-sans", description: tokens.sans });
    console.log(`--font-sans = ${tokens.sans}`);
  });

  test("Instrument Serif is self-hosted and sets the landing hero sentence from 768 px up (weight 400)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const serif = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--font-serif").trim());
    const family = families(serif)[0];
    expect(family, serif).toMatch(/instrumentSerif/i);
    const h1 = await page.getByRole("heading", { level: 1 }).evaluate((el) => {
      const cs = getComputedStyle(el);
      return { family: cs.fontFamily, size: parseFloat(cs.fontSize), weight: cs.fontWeight };
    });
    expect(families(h1.family)[0]).toBe(family);
    expect(h1.size).toBeGreaterThanOrEqual(28);
    expect(h1.weight).toBe("400");
    await page.evaluate(() => document.fonts.ready);
    const loaded = await page.evaluate(() => Array.from(document.fonts).filter((f) => f.status === "loaded").map((f) => f.family.replace(/['"]/g, "")));
    expect(loaded).toContain(family);
  });

  test("Plex Sans and Plex Mono faces load on the landing page", async ({ page }) => {
    await page.goto("/");
    const tokens = await page.evaluate(() => {
      const cs = getComputedStyle(document.documentElement);
      return { sans: cs.getPropertyValue("--font-sans").trim(), mono: cs.getPropertyValue("--font-mono").trim() };
    });
    const plexSans = families(tokens.sans)[0];
    const plexMono = families(tokens.mono)[0];
    await page.evaluate(() => document.fonts.ready);
    await expect
      .poll(
        async () =>
          page.evaluate(() => Array.from(document.fonts).filter((f) => f.status === "loaded").map((f) => f.family.replace(/['"]/g, ""))),
        { message: "self-hosted faces should be loaded" },
      )
      .toContain(plexSans);
    // Plex Mono is only fetched when mono text is on the page; check it is declared at least.
    const declared = await page.evaluate(() => Array.from(document.fonts).map((f) => f.family.replace(/['"]/g, "")));
    expect(declared).toContain(plexMono);
  });

  test("a Kannada reply renders in the Noto Sans Kannada face, not a system fallback", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click(); // the recorded offer is English; its order reply is Kannada
    const log = page.getByTestId("chat-log");
    await log.locator(".chat-msg--agent").first().getByRole("button", { name: "Add to cart" }).click();
    const bubble = log.locator(".chat-msg--agent").nth(1);
    await expect(bubble).toContainText("ಆರ್ಡರ್");
    const tokens = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim());
    const list = families(tokens);
    const plexSans = list[0];
    const notoKannada = list.find((f) => /kannada/i.test(f) && !/fallback/i.test(f))!;
    await page.evaluate(() => document.fonts.ready);
    const loaded = await page.evaluate(() =>
      Array.from(document.fonts).filter((f) => f.status === "loaded").map((f) => f.family.replace(/['"]/g, "")),
    );
    expect(loaded, `loaded font faces: ${loaded.join(", ")}`).toContain(notoKannada);
    expect(loaded, `loaded font faces: ${loaded.join(", ")}`).toContain(plexSans);
  });
});
