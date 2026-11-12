import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import { defineConfig, type Plugin } from "vite";

const root = dirname(fileURLToPath(import.meta.url));

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

/**
 * Shell pages (splash + fatal error). Electron-vite builds this config; the
 * pages stay a separate Vite app from the Dashboard.
 */
export default defineConfig({
  root,
  plugins: [react(), svgr(), shellThemeBootPlugin()],
  build: {
    // electron-vite leaves the renderer unminified by default, which would ship
    // ~640 kB of React to paint two static pages.
    minify: "esbuild",
    rollupOptions: {
      input: {
        splash: resolve(root, "splash.html"),
        error: resolve(root, "error.html"),
      },
    },
  },
});
