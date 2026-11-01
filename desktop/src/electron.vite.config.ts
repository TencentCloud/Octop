import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import type { Plugin } from "vite";

/**
 * Vite injects the extracted stylesheet at the start of `<head>`. The theme
 * script has to run first, or a dark splash paints with the light variables
 * for a frame. The script body stays in the HTML so its CSP hash can be checked.
 */
function shellThemeBootPlugin(): Plugin {
  return {
    name: "octop-shell-theme-boot",
    transformIndexHtml: {
      order: "post",
      handler(html) {
        const matched = html.match(/<script id="octop-shell-theme">[\s\S]*?<\/script>/);
        if (!matched) return html;
        const script = matched[0];
        return html
          .replace(script, "")
          .replace(/<head([^>]*)>/, `<head$1>\n    ${script}`);
      },
    },
  };
}

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
        input: {
          index: resolve(__dirname, "preload/index.ts"),
          // Separate, much smaller bridge for the shell's own pages (splash +
          // fatal error). They must not be handed the Dashboard's API.
          early: resolve(__dirname, "preload/early.ts"),
        },
      },
    },
  },
  renderer: {
    plugins: [shellThemeBootPlugin()],
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
