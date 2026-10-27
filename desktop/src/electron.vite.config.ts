import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

// Build entry points: main process, preload bridge, and the Early Window
// splash page (plain HTML, no framework).
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
        input: { index: resolve(__dirname, "preload/index.ts") },
      },
    },
  },
  renderer: {
    root: resolve(__dirname, "renderer"),
    build: {
      rollupOptions: {
        input: { splash: resolve(__dirname, "renderer/splash.html") },
      },
    },
  },
});
