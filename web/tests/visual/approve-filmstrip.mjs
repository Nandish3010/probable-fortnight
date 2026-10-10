// Captures the Approve moment as a filmstrip, for a person to look at (not part of `npm test`).
//   node tests/visual/approve-filmstrip.mjs [outDir]
// Needs the mock-mode dev server on port 3100 (NEXT_PUBLIC_TAAL_MOCK=1 npx next dev -p 3100).
// For each of 1280x800 and 375x812, light and dark: before the click, +0.3 s and +1 s while the
// request is in flight (the mock is slowed so the wait stays on screen), right after the response,
// +0.5 s, +1.2 s, and settled. Each frame is the viewport; a contact sheet puts them side by side.
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL || "http://localhost:3100";
const OUT = process.argv[2] || "/Users/NS/AI_builder_taal/coordination/ui-ux/shots_phase2b";
fs.mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "phone", width: 375, height: 812 },
];
const SCHEMES = ["light", "dark"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch();
for (const vp of VIEWPORTS) {
  for (const scheme of SCHEMES) {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      colorScheme: scheme,
      deviceScaleFactor: 1,
      hasTouch: vp.name === "phone",
      isMobile: vp.name === "phone",
    });
    const page = await ctx.newPage();
    await page.addInitScript(() => {
      localStorage.setItem("taal_mock_delay", JSON.stringify({ "/approve": 2600, "/chat": 400 }));
    });
    await page.goto(BASE + "/");
    await page.getByRole("button", { name: "Run the 60-second beat" }).click();
    await page.getByTestId("beat-panel").waitFor();
    await sleep(600);

    const frames = [];
    const snap = async (label) => {
      const file = `approve-${vp.name}-${scheme}-${String(frames.length + 1).padStart(2, "0")}-${label}.png`;
      await page.screenshot({ path: path.join(OUT, file) });
      frames.push({ label, file });
    };

    await snap("before");
    await page.getByRole("button", { name: "Approve" }).click();
    const t0 = Date.now();
    await sleep(300);
    await snap("submitting-0.3s");
    await sleep(Math.max(0, 1000 - (Date.now() - t0)));
    await snap("submitting-1s");
    // right after the response: the first tick appears
    await page.locator('[data-testid="approve-step"][data-state="done"]').first().waitFor({ timeout: 15000 });
    await snap("response-T0");
    await sleep(500);
    await snap("T0-plus-0.5s");
    await sleep(700);
    await snap("T0-plus-1.2s");
    await page.locator('[data-testid="approve-result"][data-phase="settled"]').waitFor({ timeout: 15000 });
    await sleep(400);
    await snap("settled");
    await page.screenshot({ path: path.join(OUT, `approve-${vp.name}-${scheme}-full.png`), fullPage: true });

    const cols = vp.name === "desktop" ? 2 : 4;
    const cellW = vp.name === "desktop" ? 640 : 300;
    const html = `<body style="margin:0;background:#888;font:12px sans-serif;display:grid;grid-template-columns:repeat(${cols},${cellW}px);gap:6px;padding:6px">${frames
      .map((f) => `<figure style="margin:0"><img src="${f.file}" style="width:${cellW}px;display:block"><figcaption style="color:#fff">${f.label}</figcaption></figure>`)
      .join("")}</body>`;
    const sheetHtml = path.join(OUT, `sheet-${vp.name}-${scheme}.html`);
    fs.writeFileSync(sheetHtml, html);
    const sheet = await ctx.newPage();
    await sheet.setViewportSize({ width: cols * (cellW + 6) + 6, height: 800 });
    await sheet.goto("file://" + sheetHtml);
    await sheet.waitForLoadState("load");
    await sheet.screenshot({ path: path.join(OUT, `sheet-${vp.name}-${scheme}.png`), fullPage: true });
    fs.unlinkSync(sheetHtml);
    await ctx.close();
  }
}
await browser.close();
console.log("wrote", OUT);
