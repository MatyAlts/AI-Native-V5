import { defineConfig, devices } from "@playwright/test"

/**
 * Playwright config para la suite E2E del piloto UNSL.
 *
 * Decisiones (ver design.md de la change):
 *  - Solo Chromium MVP — defensa doctoral no usa Firefox/WebKit.
 *  - `fullyParallel: false` — el journey 5 depende del 4 (cross-frontend).
 *  - `retries: 0` — no enmascarar flakiness durante MVP.
 *  - Artefactos en `.dev-logs/e2e-artifacts/` (gitignored).
 *  - GlobalSetup falla rapido si servicios/frontends/workers/seed no estan.
 */
export default defineConfig({
  testDir: "./journeys",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["html", { open: "on-failure", outputFolder: "playwright-report" }], ["list"]],
  outputDir: ".dev-logs/e2e-artifacts",
  globalSetup: "./global-setup.ts",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    headless: true,
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
})
