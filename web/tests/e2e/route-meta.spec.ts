import { test, expect } from "@playwright/test";

// Every route has its own <title> and description (Next metadata) and exactly one visible h1.
const ROUTES: { path: string; title: string }[] = [
  { path: "/", title: "Taal: sell what the forecast says you'll throw away" },
  { path: "/desk", title: "Play Desk | Taal" },
  { path: "/phone", title: "Phone view | Taal" },
  { path: "/chat", title: "Chat | Taal" },
  { path: "/outcomes", title: "Outcomes | Taal" },
  { path: "/feedback", title: "Feedback | Taal" },
];

for (const r of ROUTES) {
  test(`${r.path}: title, description and a single visible h1`, async ({ page }) => {
    await page.goto(r.path);
    await expect(page).toHaveTitle(r.title);
    const desc = await page.locator('meta[name="description"]').getAttribute("content");
    expect(desc && desc.length > 20, `description of ${r.path}`).toBeTruthy();
    const h1s = page.getByRole("heading", { level: 1 });
    await expect(h1s).toHaveCount(1);
    await expect(h1s.first()).toBeVisible();
    // visible: not the clipped visually-hidden pattern
    const box = await h1s.first().boundingBox();
    expect(box!.width).toBeGreaterThan(40);
    // none of the pages leaks the old "judge mode" title or the hidden "Taal" placeholder h1
    expect(await page.title()).not.toMatch(/judge mode/i);
  });
}
