import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import rendererConfig from "./renderer/vite.config";

function gitStamp(args: string[], envName: string): string {
  const fromEnv = process.env[envName]?.trim();
  if (fromEnv) return fromEnv;
  try {
    return execFileSync("git", args, {
      cwd: resolve(__dirname, "../.."),
      encoding: "utf8",
      timeout: 5000,
      windowsHide: true,
    }).trim();
  } catch {
    return "";
  }
}

// Build entries: main process, preload bridge, and the shell's own pages
// (splash + fatal-error Result). The renderer is its own Vite + React app
// (`renderer/vite.config.ts`); it imports nothing from the Dashboard bundle,
// which is what lets the shell paint a real page before the Python sidecar —
// and the Dashboard — exist at all.
export default defineConfig({
  main: {
    define: {
      "process.env.OCTOP_GIT_COMMIT": JSON.stringify(gitStamp(["rev-parse", "HEAD"], "GITHUB_SHA")),
      "process.env.OCTOP_GIT_DATE": JSON.stringify(
        gitStamp(["log", "-1", "--format=%cI"], "OCTOP_GIT_DATE"),
      ),
    },
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
  renderer: rendererConfig,
});
