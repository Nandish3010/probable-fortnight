import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Persona walkthrough against the REAL stack: `make api` on 8080 and `make web` on 3000 with
// NEXT_PUBLIC_TAAL_API_URL=http://localhost:8080 (mock mode off). Run with `make live-test`.
function findChromium(): string | undefined {
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !fs.existsSync(root)) return undefined;
  for (const d of fs.readdirSync(root).filter((d) => /^chromium-\d+$/.test(d))) {
    const p = path.join(root, d, "chrome-linux/chrome");
    if (fs.existsSync(p)) return p;
  }
  return undefined;
}
const executablePath = findChromium();

export default defineConfig({
  testDir: "./tests/live",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../eval/runs/live-results",
  use: {
    baseURL: process.env.TAAL_WEB_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /priya\.spec\.ts/ },
  ],
});
