import type { Plugin } from "vite";

/**
 * Vite's `@vite/client` always opens a WebSocket. When that socket drops it
 * does `waitForSuccessfulPing` → `location.reload()`. On Safari + listen
 * port 80 (empty `location.port`) / LAN / `hmr: false`, the socket fails
 * repeatedly and the whole SPA looks like it is "periodically refreshing".
 *
 * `server.hmr: false` does NOT disable this client (Vite still uses the WS
 * for overlays / full-reload). Patch the disconnect path instead.
 */
export function suppressViteDisconnectReload(): Plugin {
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
