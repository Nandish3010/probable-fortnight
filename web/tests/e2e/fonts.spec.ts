import { test, expect } from "@playwright/test";

// app/globals.css used to declare --font-sans / --font-mono on :root under the same names as the
// next/font variables in app/layout.tsx, which replaced IBM Plex with the system stack on every
// page. The next/font variables are now --font-plex-sans, --font-plex-mono and --font-noto-kannada,
// and the tokens list them first.
test.describe("fonts", () => {
  test("--font-sans starts with IBM Plex Sans, then Noto Sans Kannada, then the system stack", async ({ page }) => {
    await page.goto("/");
    const tokens = await page.evaluate(() => {
      const cs = getComputedStyle(document.documentElement);
      return {
        sans: cs.getPropertyValue("--font-sans").trim(),
        mono: cs.getPropertyValue("--font-mono").trim(),
        bodyFamily: getComputedStyle(document.body).fontFamily,
      };
    });
    // next/font renames the family (e.g. '__IBM_Plex_Sans_a1b2c3'); the readable name stays in it.
    expect(tokens.sans).toMatch(/^['"]?(__)?IBM[_ ]Plex[_ ]Sans/i);
    const order = (s: string, re: RegExp) => s.search(re);
    expect(order(tokens.sans, /Noto[_ ]Sans[_ ]Kannada/i)).toBeGreaterThan(order(tokens.sans, /IBM[_ ]Plex[_ ]Sans/i));
    expect(order(tokens.sans, /-apple-system/)).toBeGreaterThan(order(tokens.sans, /Noto[_ ]Sans[_ ]Kannada/i));
    expect(tokens.mono).toMatch(/^['"]?(__)?IBM[_ ]Plex[_ ]Mono/i);
    // and the page really uses it
    expect(tokens.bodyFamily).toMatch(/IBM[_ ]Plex[_ ]Sans/i);
    test.info().annotations.push({ type: "--font-sans", description: tokens.sans });
    console.log(`--font-sans = ${tokens.sans}`);
  });

  test("a Kannada reply renders in Noto Sans Kannada, not a system fallback", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("button", { name: "Send" }).click(); // Meena's offer is in Kannada
    const bubble = page.getByTestId("chat-log").locator(".chat-msg--agent").first();
    await expect(bubble).toContainText("ಇಂದು");
    await page.evaluate(() => document.fonts.ready);
    const loaded = await page.evaluate(() =>
      Array.from(document.fonts).filter((f) => f.status === "loaded").map((f) => f.family.replace(/['"]/g, "")),
    );
    expect(loaded.some((f) => /Noto[_ ]Sans[_ ]Kannada/i.test(f)), `loaded font faces: ${loaded.join(", ")}`).toBe(true);
    expect(loaded.some((f) => /IBM[_ ]Plex[_ ]Sans/i.test(f)), `loaded font faces: ${loaded.join(", ")}`).toBe(true);
  });
});
