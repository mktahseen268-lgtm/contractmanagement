import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright, used here for the accessibility scan (Phase 9, item 5).
 *
 * `webServer` builds and starts the app itself so CI does not need a separate step to keep in
 * sync with this config. `reuseExistingServer` locally, because rebuilding between runs while
 * iterating on a fix is most of the wall-clock time.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3000",
    trace: "on-first-retry",
    // A real viewport, not a phone: the accessibility scan is about the default experience.
    // Narrow-screen behaviour gets its own project below.
    ...devices["Desktop Chrome"],
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    // Phase 9, item 8: the signing and approval surfaces have to work on a phone, so they are
    // scanned at a phone viewport too. A layout that only passes at 1280px wide has not been
    // checked where it actually gets used.
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npm run build && npm run start",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
