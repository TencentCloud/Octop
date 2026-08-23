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

/**
 * Vite's `@vite/client` always opens a WebSocket. When that socket drops it
 * does `waitForSuccessfulPing` → `location.reload()`. On Safari + listen
 * port 80 (empty `location.port`) / LAN / `hmr: false`, the socket fails
 * repeatedly and the whole SPA looks like it is "periodically refreshing".
 *
 * `server.hmr: false` does NOT disable this client (Vite still uses the WS
 * for overlays / full-reload). Patch the disconnect path instead.
 */
function suppressViteDisconnectReload(): Plugin {
  return {
    name: "octop-suppress-vite-disconnect-reload",
    apply: "serve",
    enforce: "pre",
    transform(code, id) {
      const isViteClient =
        id.includes("vite/dist/client/client.mjs") ||
        id.includes("vite/dist/client/client.js") ||
        /(?:^|\/)@vite\/client(?:\?|$)/.test(id);
      if (!isViteClient) return;
      if (!code.includes("server connection lost")) return;

      let next = code.replace(
        /await waitForSuccessfulPing\(([^)]*)\);\s*location\.reload\(\);/g,
        "await waitForSuccessfulPing($1); console.warn('[vite] WS restored; reload suppressed');",
      );
      // Fallback if formatting differs across Vite versions.
      if (next === code && code.includes("location.reload()")) {
        next = code.replace(
          /console\.log\(`\[vite\] server connection lost\. Polling for restart\.\.\.`\);[\s\S]*?location\.reload\(\);/,
          'console.warn("[vite] server connection lost (reload suppressed)"); return;',
        );
      }
      if (next === code) return;
      return { code: next, map: null };
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Empty = same-origin; frontend and backend served together, no hardcoded host.
  const apiBaseUrl = env.BASE_URL ?? "";
  // Allow overriding the backend port via VITE_API_PORT env variable (default: 8088)
  const apiPort = process.env.VITE_API_PORT ?? env.VITE_API_PORT ?? "8088";

  const isProd = mode === "production";
  const analyze = env.ANALYZE === "true";
  // Dev server defaults to Vite's :5173. Override with VITE_DEV_PORT (e.g. 80
  // for LAN / same-origin setups). Must stay in sync with server.hmr.clientPort.
  const devServerPort = Number(process.env.VITE_DEV_PORT || 5173);

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
      suppressViteDisconnectReload(),
      react(),
      VitePWA({
        // prompt: new SW stays in waiting until the user accepts via
        // PwaUpdatePrompt → applyUpdate() → SKIP_WAITING. Avoid autoUpdate
        // skipWaiting + page reload loops (especially Safari/WebKit).
        registerType: "prompt",
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
          // Precache hashed entry + vendor chunks. Do NOT precache index.html:
          // Cache-First on the shell pins a stale HTML that points at deleted
          // hashes after deploy (white screen until a hard refresh).
          globPatterns: [
            "assets/index.*.js",
            "assets/vendor-*.js",
            "assets/*.{css,woff2}",
          ],
          // vendor-antd (incl. the ColorPicker color engine) exceeds the
          // 2 MiB workbox default; raise the precache limit so it stays
          // offline-available instead of silently skipped.
          maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
          // FastAPI already serves the SPA fallback. A Workbox NavigationRoute
          // would Cache-First the old shell; use NetworkFirst below instead.
          navigateFallback: null,
          // Take control on first activation so Chrome can fire beforeinstallprompt.
          clientsClaim: true,
          // Do not activate updated workers until the user confirms (SKIP_WAITING).
          skipWaiting: false,
          runtimeCaching: [
            {
              // Always revalidate the HTML shell so a new deploy is picked up
              // without a hard refresh. Last good copy is kept for offline.
              urlPattern: ({ request }) => request.mode === "navigate",
              handler: "NetworkFirst",
              options: {
                cacheName: "html-shell",
                networkTimeoutSeconds: 3,
                expiration: {
                  maxEntries: 8,
                  maxAgeSeconds: 24 * 60 * 60,
                },
              },
            },
            {
              // Vite emits content-hashed assets (assets/name.[hash].js).
              // CacheFirst is correct: a new deploy uses new URLs.
              // NetworkFirst would prefer a post-deploy 404 over the cache.
              urlPattern: /\/assets\/.*\.(js|css)$/,
              handler: "CacheFirst",
              options: {
                cacheName: "static-chunks",
                expiration: {
                  maxEntries: 200,
                  maxAgeSeconds: 30 * 24 * 60 * 60,
                },
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
      port: devServerPort,
      allowedHosts: true,
      // NEVER default to `hmr: false` — Vite still injects @vite/client and a
      // failed WS then triggers location.reload() loops. Pin clientPort so
      // Safari on privileged ports (e.g. :80 via VITE_DEV_PORT) does not build
      // `ws://host:/` when location.port is empty.
      hmr: {
        clientPort: Number(process.env.VITE_HMR_CLIENT_PORT || devServerPort),
      },
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
          // Only proxy API websockets — do not steal Vite's HMR upgrade on `/`.
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
