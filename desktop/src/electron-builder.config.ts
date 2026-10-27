import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// electron-builder does not support ESM config directly; this file is written as
// CJS-compatible TypeScript but consumed through the JS build output. It pins the
// shell, the bundled Dashboard assets, and the portable runtime into ONE release.
const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf8")) as {
  version: string;
};

export default {
  appId: "cloud.octop.desktop",
  productName: "Octop",
  // The portable runtime zip lives OUTSIDE asar so C-extensions/.so/DLLs load.
  asar: true,
  asarUnpack: ["resources/portable/**"],
  extraResources: [
    { from: "resources/portable", to: "portable" },
    { from: "resources/dashboard", to: "dashboard" },
  ],
  files: ["out/**/*", "package.json"],
  directories: { output: "release", buildResources: "resources" },
  mac: {
    target: ["dmg", "zip"],
    category: "public.app-category.productivity",
    icon: "resources/icon.icns",
    hardenedRuntime: true,
    gatekeeperAssess: false,
    // Signing/notarization are wired through CSC_LINK / APPLE_* env in CI, not here.
  },
  win: {
    icon: "resources/icon.ico",
    target: [{ target: "nsis", arch: ["x64", "arm64"] }],
    // Keep Authenticode signing via CSC_LINK / WIN_CSC_LINK in CI.
  },
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    perMachine: false,
    deleteAppDataOnUninstall: false,
  },
  linux: {
    target: ["AppImage", "deb", "rpm"],
    icon: "resources/icon.png",
    category: "Utility",
    maintainer: "Octop",
  },
  publish: null,
} as const;
