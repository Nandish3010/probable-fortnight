import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// Use the pre-installed Chromium when PLAYWRIGHT_BROWSERS_PATH points at one;
// otherwise fall back to the default "chromium" channel resolution.
function findChromium(): string | undefined {
  const root = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (!root || !fs.existsSync(root)) return undefined;
  const dirs = fs
    .readdirSync(root)
    .filter((d) => /^chromium(_headless_shell)?-\d+$/.test(d))
    .sort((a, b) => (a.startsWith("chromium-") ? -1 : 1) - (b.startsWith("chromium-") ? -1 : 1));
  for (const d of dirs) {
    for (const bin of ["chrome-linux/chrome", "chrome-linux/headless_shell", "chrome-mac/Chromium.app/Contents/MacOS/Chromium"]) {
      const p = path.join(root, d, bin);
      if (fs.existsSync(p)) return p;
    }
  }
  return undefined;
}

const executablePath = findChromium();
const port = Number(process.env.PORT || 3100);
const baseURL = `http://localhost:${port}`;
const useStart = process.env.TAAL_E2E_SERVER === "start";

// The guided tour opens by itself on a visitor's first beat (lib/tour.ts). Every spec but the tour's
// own starts with it switched off through its kill switch, so a first-visit popover does not sit on
// top of unrelated flows; tests/e2e/tour.spec.ts opts back in with an empty storage state.
const tourOff = { cookies: [], origins: [{ origin: baseURL, localStorage: [{ name: "taal_tour_off", value: "1" }] }] };

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: process.env.CI ? "line" : [["list"]],
  use: {
    baseURL,
    storageState: tourOff,
    trace: "retain-on-failure",
    launchOptions: executablePath ? { executablePath } : {},
  },
  projects: [
    // Specs named *-phone.spec.ts are about the phone layout and run on the Pixel 7 project only.
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /-phone\.spec\.ts/ },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /(phone|feedback)\.spec\.ts/ },
  ],
  webServer: {
    command: useStart ? `npm run build && npx next start -p ${port}` : `npx next dev -p ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { NEXT_PUBLIC_TAAL_MOCK: "1", PORT: String(port) },
  },
});
