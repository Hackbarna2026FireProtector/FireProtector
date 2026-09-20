import { defineConfig } from "@playwright/test";

/**
 * Smoke test against `make serve` (Flask serving the built app on :5000,
 * DATA_MODE=mock). CI starts the server before running this.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5000",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
