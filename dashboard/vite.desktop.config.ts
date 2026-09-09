import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

function serveDesktopAtRoot(): Plugin {
  return {
    name: "octop-desktop-shell-index",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (!req.url) {
          next();
          return;
        }
        const url = new URL(req.url, "http://localhost");
        if (url.pathname === "/" || url.pathname === "/index.html") {
          req.url = `/desktop.html${url.search}${url.hash}`;
        }
        next();
      });
    },
    transformIndexHtml(html) {
      if (html.includes("/wails/runtime.js")) return html;
      return html.replace(
        "</head>",
        '    <script type="module" src="/wails/runtime.js"></script>\n  </head>',
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), serveDesktopAtRoot()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom"],
  },
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
  server: {
    host: "localhost",
    port: Number(process.env.WAILS_VITE_PORT || 9245),
    strictPort: true,
  },
  publicDir: false,
  build: {
    outDir: path.resolve(__dirname, "dist-desktop"),
    emptyOutDir: true,
    sourcemap: false,
    cssCodeSplit: true,
    rollupOptions: {
      input: {
        index: path.resolve(__dirname, "desktop.html"),
      },
      external: ["/wails/runtime.js"],
    },
  },
});
