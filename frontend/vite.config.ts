/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 5102 is fixed by the asset-register contract — it is where the API is
// expected to be, and docker-compose publishes it there. Override with
// BACKEND_URL when running the API straight on the host on another port.
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:5102";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // /api is the decision layer this UI talks to. The other three are the
      // contract routes at the root, proxied as well so one origin serves
      // everything while poking at the API from the browser.
      "/api": { target: BACKEND, changeOrigin: true },
      "/assets": { target: BACKEND, changeOrigin: true },
      "/fire": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    css: false,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
