import { webcrypto } from "node:crypto";
import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "path";

// serialize-javascript@7 (pulled in by vite-plugin-pwa → @rollup/plugin-terser)
// expects Web Crypto globals during `vite build`. Node <19 does not define them.
if (typeof globalThis.crypto === "undefined") {
  Object.defineProperty(globalThis, "crypto", {
    value: webcrypto,
    configurable: true,
  });
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Empty = same-origin; frontend and backend served together, no hardcoded host.
  const apiBaseUrl = env.BASE_URL ?? "";
  // Allow overriding the backend port via VITE_API_PORT env variable (default: 8088)
  const apiPort = process.env.VITE_API_PORT ?? env.VITE_API_PORT ?? "8088";

  const isProd = mode === "production";
  const analyze = env.ANALYZE === "true";

  // Conditionally load the visualizer plugin (sync require to avoid async issues)
  const extraPlugins: Plugin[] = [];
  if (analyze) {
    try {
      const { visualizer } =
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        require("rollup-plugin-visualizer") as typeof import("rollup-plugin-visualizer");
      extraPlugins.push(
        visualizer({
          open: true,
          filename: "dist/bundle-stats.html",
          gzipSize: true,
          brotliSize: true,
        }) as unknown as Plugin,
      );
    } catch {
      console.warn(
        "rollup-plugin-visualizer not installed, skipping bundle analysis",
      );
    }
  }

  return {
    build: {
      outDir: path.resolve(__dirname, "../src/octop/dashboard"),
      emptyOutDir: true,
      chunkSizeWarningLimit: 1600,
      // Limit Rollup worker concurrency to prevent OOM on memory-constrained hosts.
      // Without this, Rollup spawns one worker per CPU core and antd's 7000+ modules
      // exhaust available RAM when there is no swap space.
      rollupOptions: {
        maxParallelFileOps: 3,
        output: {
          entryFileNames: "assets/index.[hash].js",
          chunkFileNames: "assets/[name].[hash].js",
          assetFileNames: "assets/[name].[hash].[ext]",
          manualChunks(id) {
            if (id.includes("node_modules")) {
              if (id.includes("react-dom")) return "vendor-react";
              if (id.includes("react-router")) return "vendor-react";
              if (/\/node_modules\/react\//.test(id)) return "vendor-react";
              // Keep rc-* with antd in one chunk. Splitting rc-* into vendor-rc
              // creates a circular chunk (vendor-rc ↔ vendor-antd) that breaks
              // production with "Cannot access 'FastColor' before initialization".
              if (id.includes("rc-")) return "vendor-antd";
              if (id.includes("/antd/")) return "vendor-antd";
              if (id.includes("antd-style")) return "vendor-antd";
              if (id.includes("@ant-design")) return "vendor-antd";
              if (id.includes("@xterm")) return "vendor-xterm";
              // mermaid + deps are dynamically imported — skip manualChunks so
              // Vite generates async chunks automatically.
              if (
                id.includes("mermaid") ||
                id.includes("cytoscape") ||
                id.includes("dagre") ||
                id.includes("elkjs") ||
                id.includes("cose-bilkent")
              )
                return undefined;
              if (
                id.includes("react-markdown") ||
                id.includes("remark-gfm") ||
                id.includes("remark-") ||
                id.includes("rehype-") ||
                id.includes("katex")
              )
                return "vendor-markdown";
              if (
                id.includes("react-syntax-highlighter") ||
                id.includes("refractor") ||
                id.includes("highlight.js")
              )
                return undefined;
              if (id.includes("lucide-react")) return "vendor-icons";
              if (
                id.includes("i18next") ||
                id.includes("ahooks") ||
                id.includes("jszip")
              )
                return "vendor-utils";
            }
          },
        },
      },
    },
    esbuild: {
      drop: isProd ? ["debugger"] : [],
      pure: isProd ? ["console.log", "console.debug", "console.info"] : [],
      // Disable identifier mangling to work around @xterm/xterm@6.0.0 crash in
      // production builds: the lib ships as pre-minified ESM with a closure
      // inside `InputHandler.requestMode` that breaks when esbuild renames
      // the outer parameter `i` during re-minification. See
      // https://github.com/xtermjs/xterm.js/issues/5800 — first DCS/CSI mode
      // query from tools like vim / htop / less / opencode triggers
      // "Uncaught ReferenceError: i is not defined" and all further input
      // is dropped. Identifier mangling saves very little vs whitespace /
      // dead-code removal, which remain on.
      minifyIdentifiers: false,
    },
    define: {
      BASE_URL: JSON.stringify(apiBaseUrl),
      MOBILE: false,
    },
    plugins: [
      react(),
      VitePWA({
        // autoUpdate: new SW activates as soon as it's installed. Combined with
        // skipWaiting + clientsClaim below, a hard-reload (Ctrl+Shift+R) once is
        // enough — every subsequent deploy is picked up automatically. Using
        // "prompt" required users to confirm each update via a UI we never
        // surfaced, so old assets kept getting served forever.
        registerType: "autoUpdate",
        // SW registration is handled in sw-register.ts for full control.
        injectRegister: false,
        // Use public/manifest.json directly instead of auto-generating one.
        manifest: false,
        // Include the offline fallback in the SW precache.
        includeAssets: [
          "offline.html",
          "logo.svg",
          "logo_name.png",
          "logo_name_dark.png",
          "pwa-192.png",
          "pwa-512.png",
          "apple-touch-icon.png",
        ],
        workbox: {
          // Precache the SPA shell and critical vendor chunks only.
          // Lazy route chunks are cached at runtime via NetworkFirst below.
          globPatterns: [
            "index.html",
            "assets/index.*.js",
            "assets/vendor-react.*.js",
            "assets/vendor-antd.*.js",
            "assets/*.{css,woff2}",
          ],
          // SPA fallback: navigate requests that miss the precache get index.html
          // so React Router can handle the route client-side. This is the correct
          // pattern for SPAs — do NOT use offline.html here or every route that
          // isn't in the precache will show the offline page instead of the app.
          navigateFallback: "/index.html",
          // Keep API, SSE and WebSocket requests completely outside SW control.
          navigateFallbackDenylist: [/^\/api/, /^\/ws/],
          // Take control of all open tabs as soon as the SW activates so Chrome
          // counts the SW as "controlling" the page and fires beforeinstallprompt.
          clientsClaim: true,
          // Activate the new SW immediately so stale assets are never served
          // after a publish. Since chunks have no content-hash in their names,
          // CacheFirst would return the old file forever without this.
          skipWaiting: true,
          runtimeCaching: [
            {
              // JS/CSS chunks have no content-hash in their names (fixed names
              // like assets/index.js). Use NetworkFirst so a new deployment is
              // picked up immediately; fall back to cache only when offline.
              urlPattern: /\/assets\/.*\.(js|css)$/,
              handler: "NetworkFirst",
              options: {
                cacheName: "static-chunks",
                networkTimeoutSeconds: 5,
                expiration: { maxAgeSeconds: 30 * 24 * 60 * 60 },
              },
            },
            {
              // 3D model and animation files (GLB / GIF) — large, cache up to 7 days.
              urlPattern: /\.(glb|gltf|gif)$/,
              handler: "CacheFirst",
              options: {
                cacheName: "3d-assets",
                expiration: { maxEntries: 60, maxAgeSeconds: 7 * 24 * 60 * 60 },
              },
            },
            {
              // Read-only API calls (chat history, files, config).
              // NetworkFirst ensures fresh data when online; cache used offline.
              urlPattern: /^\/api\/(chats|agent\/files|agent\/memory)/,
              handler: "NetworkFirst",
              options: {
                cacheName: "api-readonly",
                networkTimeoutSeconds: 5,
                expiration: { maxEntries: 50, maxAgeSeconds: 5 * 60 },
              },
            },
            {
              // Web fonts (woff2) — essentially permanent.
              urlPattern: /\.woff2?$/,
              handler: "CacheFirst",
              options: {
                cacheName: "fonts",
                expiration: { maxAgeSeconds: 365 * 24 * 60 * 60 },
              },
            },
          ],
        },
      }),
      ...extraPlugins,
    ],
    css: {
      modules: {
        localsConvention: "camelCase",
        generateScopedName: "[name]__[local]__[hash:base64:5]",
      },
      preprocessorOptions: {
        less: {
          javascriptEnabled: true,
        },
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
      dedupe: ["react", "react-dom"],
    },
    server: {
      host: "0.0.0.0",
      port: 80,
      allowedHosts: true,
      watch: {
        // Exclude large directories that do not need watching to reduce inotify fd usage.
        ignored: [
          "**/node_modules/**",
          "**/.git/**",
          "**/dist/**",
          "**/build/**",
        ],
        usePolling: false,
      },
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    optimizeDeps: {
      // TokenUsage lazy-loads recharts; without pre-bundling the first request
      // often 504s while Vite optimizes on demand.
      include: ["recharts"],
    },
  };
});
