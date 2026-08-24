/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: true,
    // Vitest defaults `mode` to "test", not "development" — it never
    // loads .env.development on its own. Rather than adding a third
    // .env.test file just for this (the frontend plan only calls for
    // development/production configs), the test environment's own
    // VITE_API_BASE_URL is defined directly here, self-contained.
    env: {
      VITE_API_BASE_URL: "http://localhost:8000/api/v1",
    },
    // "forks" (Vitest's default pool) times out spawning worker child
    // processes in this environment — confirmed empirically, not
    // assumed (every test file but the first failed with "Timeout
    // waiting for worker to respond"). "threads" uses worker_threads
    // instead of separate OS processes and is the standard, documented
    // fix for exactly this class of failure.
    pool: "threads",
    // Same sandboxed-environment slowness as above, hitting a different
    // symptom: Vitest's 5000ms default per-test timeout is too tight for
    // a Stage 2 form test that types into several fields via
    // @testing-library/user-event (confirmed empirically — every such
    // test timed out at exactly 5000ms while simpler tests passed in
    // well under a second). 15s gives real per-key-event typing enough
    // room here without masking a genuinely hung test elsewhere.
    testTimeout: 15000,
  },
});
