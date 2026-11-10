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
  : `Octop-desktop-\${os}-\${arch}-\${version}.\${ext}`;
const productName = "Octop";

export default {
  extraMetadata: { version: electronVersion },
  artifactName,
  appId: "com.tencent.octop",
  productName,
  // extraResources places the portable tree outside asar. The shell reads
  // Dashboard from portable/packages/octop/dashboard, so it is not copied again.
  asar: true,
  // Bare "en" also keeps en-* region packs. zh_CN does not keep zh_TW.
  // zh-Hans InfoPlist.strings are written in afterPack, after this filter.
  electronLanguages: ["en", "zh_CN"],
  extraResources: [
    { from: "resources/icon.ico", to: "icon.ico" },
    { from: "resources/icon.png", to: "icon.png" },
    { from: "resources/portable", to: "portable" },
    // deb postinst sources this after files are unpacked. postrm inlines a copy
    // because dpkg deletes the install tree first.
    { from: "build/linux-desktop-shortcut.sh", to: "linux-desktop-shortcut.sh" },
  ],
  files: ["out/**/*", "package.json"],
  directories: { output: "release", buildResources: "resources" },
  mac: {
    target: ["dmg", "zip"],
    category: "public.app-category.productivity",
    // Full-bleed opaque icns. Transparent corners make Finder draw a gray plate.
    icon: "resources/icon.icns",
    // Releases are unsigned and not notarized. identity: null is required:
    // electron-builder otherwise takes the empty-password signing path and
    // aborts mid mac pipeline.
    identity: null,
    hardenedRuntime: false,
    gatekeeperAssess: false,
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
  // develop's drag-to-Applications art (resources/dmg-background.jpeg).
  // The 600×400 PNG sets the window size; the @2x sibling becomes the HiDPI TIFF.
  // Coordinates are icon centers, on the chevron.
  dmg: {
    background: "resources/dmg-background.png",
    iconSize: 128,
    contents: [
      { x: 154, y: 237, type: "file" },
      { x: 454, y: 237, type: "link", path: "/Applications" },
    ],
  },
  win: {
    icon: "resources/icon.ico",
    // CI passes the native runner architecture, never cross-package both here.
    target: ["nsis"],
  },
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    perMachine: false,
    deleteAppDataOnUninstall: false,
    // The finish page creates the desktop shortcut after the user confirms.
    // Silent installs still create it unless --no-desktop-shortcut is passed.
    createDesktopShortcut: false,
    // Expands resources/portable/Octop-portable-*.zip into resources/sidecar
    // with tar.exe. The 40k-file tree is not packed as individual NSIS files.
    include: "build/installer.nsh",
  },
  linux: {
    target: ["deb", "rpm"],
    executableName: "octop",
    icon: "resources/icon.png",
    category: "Utility",
    maintainer: "Octop",
  },
  deb: {
    // package.json name is octop-desktop. fpm package names live on the target,
    // not on linux (LinuxConfiguration rejects packageName).
    packageName: "octop",
    // Neither apt nor rpm has a finish page. The install script places a
    // desktop icon for the account that ran the install (or each normal
    // account when the installer is only root). A later upgrade refreshes an
    // icon that is still there. The scripts also accept rpm's numeric $1.
    afterInstall: "build/linux-after-install.sh",
    afterRemove: "build/linux-after-remove.sh",
  },
  rpm: {
    packageName: "octop",
    afterInstall: "build/linux-after-install.sh",
    afterRemove: "build/linux-after-remove.sh",
  },
  publish: null,
} as const;
