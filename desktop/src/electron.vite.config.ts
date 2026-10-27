import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";

// Build entries: main process, preload bridge, and the shell's own pages
// (splash + fatal-error Result). The renderer is a self-contained React app: it
// imports nothing from the Dashboard bundle, which is what lets the shell paint
// a real page before the Python sidecar — and the Dashboard — exist at all.
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
    // Deliberately no @vitejs/plugin-react: esbuild already compiles TSX with the
    // automatic JSX runtime ("jsx": "react-jsx" in tsconfig), and two static
    // pages gain nothing from Fast Refresh that justifies pulling Babel in.
    build: {
      // electron-vite leaves the renderer unminified by default, which would ship
      // ~640 kB of React to paint two static pages.
      minify: "esbuild",
      rollupOptions: {
        input: {
          splash: resolve(__dirname, "renderer/splash.html"),
          error: resolve(__dirname, "renderer/error.html"),
        },
      },
    },
  },
});
