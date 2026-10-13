import { defineConfig } from "@playwright/test";

const PORT = Number(process.env.KIOSK_E2E_PORT ?? 8199);
const ADMIN_PORT = Number(process.env.KIOSK_E2E_ADMIN_PORT ?? 8198);

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 45_000,
  // One server with one set of settings: the specs run one after the other and restore what they change.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    browserName: "chromium",
    locale: "de-DE",
    timezoneId: "Europe/Berlin",
  },
  webServer: {
    command: "node tests/e2e/serve.mjs",
    url: `http://127.0.0.1:${PORT}/api/health`,
    // A fresh server every run: the admin spec starts with the first-time setup.
    reuseExistingServer: false,
    timeout: 30_000,
    env: { KIOSK_E2E_PORT: String(PORT), KIOSK_E2E_ADMIN_PORT: String(ADMIN_PORT) },
  },
});
