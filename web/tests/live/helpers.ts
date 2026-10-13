import { expect, type Page } from "@playwright/test";

export const API = process.env.TAAL_API_URL || "http://localhost:8080";
export const SHOTS = "../eval/runs/screens";

export function visitorHeaders(id: string) {
  return { "X-Taal-Visitor": id, "Content-Type": "application/json" };
}

/** Seed the browser's visitor id (lib/visitor.ts reads localStorage) and reset that sandbox. */
export async function asVisitor(page: Page, id: string) {
  await page.addInitScript((vid) => {
    try { localStorage.setItem("taal_visitor", vid); } catch {}
  }, id);
  await page.request.post(`${API}/reset`, { headers: visitorHeaders(id) });
}

const SHOT_MAX_H = 3590; // clip limit: the capture viewport is 3600 px tall

/**
 * Full-page capture that stays correct on the sticky-header layout. Playwright's `fullPage`
 * stitches the page by scrolling, which on this UI paints the sticky nav mid-page and leaves the
 * beat panel blank (content that mounts or animates on scroll). Instead: a tall viewport of the
 * same width (so nothing re-lays out as a phone and no breakpoint changes), reduced motion, the
 * sticky header made static and the Next dev badge hidden for the shot, then a clip from the top
 * to the bottom of the real content. The viewport and page state are restored afterwards.
 */
export async function shot(page: Page, name: string) {
  const original = page.viewportSize();
  const width = original?.width ?? 1280;
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width, height: 3600 });
  const style = await page.addStyleTag({
    content: "nextjs-portal, [data-nextjs-toast], [data-nextjs-dev-tools-button] { display: none !important; } .top-nav { position: static !important; }",
  });
  try {
    await page.evaluate(() => window.scrollTo(0, 0));
    // the Approve toast ("Approved. Taal will hold back ...") floats over the header row; close it
    const toast = page.getByRole("button", { name: /^(close|dismiss)/i });
    if (await toast.count()) await toast.first().click().catch(() => {});
    await page.waitForTimeout(500);
    // let any lazily mounted block settle at the new size
    const height = await page.evaluate(() => {
      let bottom = 0;
      document.body.querySelectorAll("*").forEach((e) => {
        const cs = getComputedStyle(e);
        if (cs.position === "fixed" || cs.display === "none") return;
        const r = e.getBoundingClientRect();
        if (r.height > 0) bottom = Math.max(bottom, r.bottom + window.scrollY);
      });
      return Math.ceil(bottom) + 24;
    });
    await page.screenshot({ path: `${SHOTS}/${name}.png`, clip: { x: 0, y: 0, width, height: Math.min(height, SHOT_MAX_H) } });
  } finally {
    await style.evaluate((el) => el.remove());
    if (original) await page.setViewportSize(original);
  }
}

export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

export async function expectNoConsoleErrors(errors: string[]) {
  // Next dev overlays and favicon 404s are noise; anything else is a defect.
  const real = errors.filter((e) => !/favicon|Download the React DevTools|hydrat/i.test(e));
  expect(real, real.join("\n")).toEqual([]);
}
