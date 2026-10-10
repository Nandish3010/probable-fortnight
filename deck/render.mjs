// Renders deck/slides.html to docs/deck.pdf and deck/png/slide_NN.png. Called by deck/build.py.
import { createRequire } from "node:module";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const { chromium } = createRequire(path.join(root, "web", "package.json"))("@playwright/test");

const pngDir = path.join(here, "png");
fs.mkdirSync(pngDir, { recursive: true });
fs.mkdirSync(path.join(root, "docs"), { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(pathToFileURL(path.join(here, "slides.html")).href, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
const slides = page.locator("section.slide");
const n = await slides.count();
if (n !== 17) throw new Error(`expected 17 slides, found ${n}`);
for (let i = 0; i < n; i++) {
  await slides.nth(i).screenshot({ path: path.join(pngDir, `slide_${String(i + 1).padStart(2, "0")}.png`) });
}
await page.pdf({ path: path.join(root, "docs", "deck.pdf"), width: "1920px", height: "1080px", printBackground: true, preferCSSPageSize: true });
await browser.close();
