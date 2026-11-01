import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import rendererConfig from "./renderer/vite.config";

// Build entries: main process, preload bridge, and the shell's own pages
// (splash + fatal-error Result). The renderer is its own Vite + React app
// (`renderer/vite.config.ts`); it imports nothing from the Dashboard bundle,
// which is what lets the shell paint a real page before the Python sidecar —
// and the Dashboard — exist at all.
export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, "main/index.ts") },
      },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          index: resolve(__dirname, "preload/index.ts"),
          // Separate, much smaller bridge for the shell's own pages (splash +
          // fatal error). They must not be handed the Dashboard's API.
          early: resolve(__dirname, "preload/early.ts"),
        },
      },
    },
  },
  renderer: rendererConfig,
});
