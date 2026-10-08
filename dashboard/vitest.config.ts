/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

/**
 * Standalone Vitest config — kept separate from ``vite.config.ts`` so:
 * 1. The PWA plugin and SPA build tweaks don't run for unit tests
 *    (they pull heavy deps and slow startup by ~3 s).
 * 2. We can keep ``test.environment`` / ``setupFiles`` in one obvious
 *    place without polluting the prod build config.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    pool: "threads",
    // Every file boots its own jsdom environment, so one test's wall time
    // depends on how busy the other 227 workers are. Measured on one machine:
    // ``ChannelsPanel > defaults Discord to all channels`` takes 1.36 s alone,
    // 3.5-4.4 s in a normal full run and 5.41 s with all cores busy, while the
    // same assertions pass throughout. The 5 s default therefore killed tests
    // that only lost a race against contention - budget for it explicitly
    // instead of racing against an untuned ceiling.
    testTimeout: 15000,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/pages/Agent/Memory/**"],
    },
  },
});
