import { defineConfig, devices } from "@playwright/test"

/**
 * Config dedicado para grabación de videos walkthrough del piloto.
 *
 * Diferencias vs `tests/e2e/playwright.config.ts`:
 *  - viewport 1920×1080 (Full HD para video pulido)
 *  - video siempre on (no retain-on-failure)
 *  - headless: false + slowMo para ritmo humano
 *  - sin globalSetup (asume stack arriba; lo validamos con health en cada spec)
 *  - timeouts mas generosos (10 min) — son walkthroughs largos
 *  - outputDir dedicado en .dev-logs/video-recording/
 */
export default defineConfig({
  testDir: ".",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../../../.dev-logs/video-recording",
  timeout: 600_000, // 10 min por video
  expect: { timeout: 15_000 },
  use: {
    headless: false,
    viewport: { width: 1920, height: 1080 },
    video: {
      mode: "on",
      size: { width: 1920, height: 1080 },
    },
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
    launchOptions: {
      slowMo: 150,
    },
  },
  projects: [
    {
      name: "video",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1920, height: 1080 },
      },
    },
  ],
})
