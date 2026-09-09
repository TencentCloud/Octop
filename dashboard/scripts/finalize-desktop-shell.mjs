// Vite keeps the source HTML filename for multi-page builds. Wails embeds
// desktop/src/assets and expects index.html at that directory root.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "../..");
const distDir = path.join(repoRoot, "dashboard", "dist-desktop");
const destDir = path.join(repoRoot, "desktop", "src", "assets");
const keep = new Set(["tray-icon.png", "tray-icon-template.png"]);

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(from, to);
    } else {
      fs.copyFileSync(from, to);
    }
  }
}

if (!fs.existsSync(distDir)) {
  throw new Error(`Desktop shell build not found: ${distDir}`);
}

fs.mkdirSync(destDir, { recursive: true });
for (const name of fs.readdirSync(destDir)) {
  if (keep.has(name)) continue;
  fs.rmSync(path.join(destDir, name), { recursive: true, force: true });
}
copyDir(distDir, destDir);

const builtHtml = path.join(destDir, "desktop.html");
const indexHtml = path.join(destDir, "index.html");
if (!fs.existsSync(builtHtml)) {
  throw new Error(`Desktop shell HTML not found: ${builtHtml}`);
}
if (fs.existsSync(indexHtml)) {
  fs.rmSync(indexHtml);
}
fs.renameSync(builtHtml, indexHtml);

let html = fs.readFileSync(indexHtml, "utf8");
if (!html.includes("/wails/runtime.js")) {
  html = html.replace(
    "</head>",
    '    <script type="module" src="/wails/runtime.js"></script>\n  </head>',
  );
  fs.writeFileSync(indexHtml, html);
}

console.log(`Wrote desktop shell ${indexHtml}`);
