import { defineConfig } from "@playwright/test";

/**
 * Smoke test against the Vite dev server, which proxies to the API on 5102.
 * Start both first: `cd backend && docker compose up -d`, then `npm run dev`.
 */
export default defineConfig({
  testDir: "./e2e",
  // A scenario with no recorded bundle runs a live Deepfire simulation, and
  // the 24-hour ensemble takes minutes rather than seconds.
  timeout: 180_000,
  retries: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
