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

export async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
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
