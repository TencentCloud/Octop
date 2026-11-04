import fs from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import type { Plugin } from "vite";

/** Root-relative AMD prefix. The browser resolves it against the page origin. */
const MONACO_VS_PREFIX = "/monaco/vs";

function monacoVsSourceDir(rootDir: string): string {
  return path.resolve(rootDir, "node_modules/monaco-editor/min/vs");
}

function monacoContentType(file: string): string {
  return path.extname(file) === ".css"
    ? "text/css; charset=utf-8"
    : "text/javascript; charset=utf-8";
}

function resolveMonacoFile(
  vsDir: string,
  url: string | undefined,
): string | null {
  const pathname = decodeURIComponent((url ?? "/").split("?")[0] ?? "/");
  const rel = pathname.replace(/^\/+/, "");
  if (!rel || rel.includes("\0")) return null;
  const root = path.resolve(vsDir);
  const file = path.resolve(root, rel);
  if (file !== root && !file.startsWith(root + path.sep)) return null;
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return null;
  return file;
}

function sendMonacoFile(
  vsDir: string,
  req: IncomingMessage,
  res: ServerResponse,
): boolean {
  const file = resolveMonacoFile(vsDir, req.url);
  if (!file) return false;
  res.statusCode = 200;
  res.setHeader("Content-Type", monacoContentType(file));
  res.setHeader("Cache-Control", "no-cache");
  fs.createReadStream(file).pipe(res);
  return true;
}

/**
 * Serve the full monaco-editor ``min/vs`` tree (loader, editor, languages,
 * and workers) from the page origin. ``@monaco-editor/loader`` otherwise
 * downloads that tree from jsDelivr, which hangs on a LAN with no outbound
 * network.
 *
 * ``rootDir`` is the dashboard directory (``vite.config.ts``'s ``__dirname``).
 */
export function monacoSameOrigin(rootDir: string): Plugin {
  return {
    name: "octop-monaco-vs",
    configureServer(server) {
      const vsDir = monacoVsSourceDir(rootDir);
      server.middlewares.use(MONACO_VS_PREFIX, (req, res) => {
        if (sendMonacoFile(vsDir, req, res)) return;
        res.statusCode = 404;
        res.end("monaco asset not found");
      });
    },
    writeBundle(options) {
      const vsDir = monacoVsSourceDir(rootDir);
      if (!fs.existsSync(vsDir)) {
        this.error(
          `monaco-editor assets missing at ${vsDir}. Install the monaco-editor dependency.`,
        );
      }
      const outDir = options.dir;
      if (!outDir) return;
      fs.cpSync(vsDir, path.join(outDir, "monaco", "vs"), { recursive: true });
    },
  };
}
