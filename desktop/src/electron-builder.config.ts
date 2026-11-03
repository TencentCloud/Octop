import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { macPrivacyExtendInfo, writeMacPrivacyLocalizations } from "./mac-privacy-plist";

// The Python release version is authoritative. electron-builder needs SemVer in
// package metadata, while bundled runtime names keep the original PEP 440 value
// (e.g. 1.0.3b1 -> 1.0.3-beta.1 in the Electron metadata only).
const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf8")) as {
  version: string;
};
const productVersion = process.env.OCTOP_VERSION ?? pkg.version;
const electronVersion = productVersion.replace(
  /^(\d+\.\d+\.\d+)(a|b|rc)(\d+)$/,
  (_match, base: string, stage: string, number: string) =>
    `${base}-${{ a: "alpha", b: "beta", rc: "rc" }[stage as "a" | "b" | "rc"]}.${number}`,
);
if (!/^\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$/.test(electronVersion)) {
  throw new Error(`Unsupported Octop release version: ${productVersion}`);
}
const artifactName = process.env.OCTOP_PLATFORM
  ? `Octop-desktop-${process.env.OCTOP_PLATFORM}-${productVersion}.\${ext}`
  : "Octop-desktop-${os}-${arch}-${version}.${ext}";
const productName = "Octop";

// Without a certificate electron-builder does not skip signing cleanly on macOS:
// it takes the "empty password will be used for code signing" path and then dies
// deeper in the pipeline with a misleading ".../desktop/src not a file". CI sets
// this for the unsigned validation mode; a real release never does.
const skipSigning = process.env.OCTOP_SKIP_SIGN === "1";

export default {
  extraMetadata: { version: electronVersion },
  artifactName,
  appId: "com.tencent.octop",
  productName,
  // extraResources places the portable zip outside asar; the runtime is extracted
  // into OCTOP_HOME before native Python extensions are loaded.
  asar: true,
  extraResources: [
    { from: "resources/portable", to: "portable" },
    { from: "resources/dashboard", to: "dashboard" },
  ],
  files: ["out/**/*", "package.json"],
  directories: { output: "release", buildResources: "resources" },
  mac: {
    target: ["dmg", "zip"],
    category: "public.app-category.productivity",
    // Full-bleed opaque icns. Transparent corners make Finder draw a gray plate.
    icon: "resources/icon.icns",
    // hardenedRuntime without an entitlement to match is rejected by codesign,
    // so it is only meaningful once there is an identity.
    ...(skipSigning ? { identity: null, hardenedRuntime: false } : { hardenedRuntime: true }),
    gatekeeperAssess: false,
    // Signing/notarization are wired through CSC_LINK / APPLE_* env in CI, not here.
    // Usage strings for microphone, speech recognition, screen capture, and the
    // local network. Accessibility has no Info.plist key.
    extendInfo: macPrivacyExtendInfo(),
  },
  afterPack(context: { electronPlatformName: string; appOutDir: string }): void {
    if (context.electronPlatformName !== "darwin") return;
    writeMacPrivacyLocalizations(
      join(context.appOutDir, `${productName}.app`, "Contents", "Resources"),
    );
  },
  win: {
    icon: "resources/icon.ico",
    // CI passes the native runner architecture, never cross-package both here.
    target: ["nsis"],
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
