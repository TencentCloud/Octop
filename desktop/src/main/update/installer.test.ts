import assert from "node:assert/strict";
import { test } from "node:test";

import type { DownloadAsset } from "./update-coordinator";
import {
  downloadFilename,
  installUpdate,
  installerKindFor,
  isSupportedKind,
  planInstall,
  type InstallHooks,
} from "./installer";

function asset(name: string, ext: string): DownloadAsset {
  return { name, ext, url: "https://download.octop.cloud/x" };
}

test("installerKindFor maps manifest extensions", () => {
  assert.equal(installerKindFor(asset("Octop.dmg", "dmg")), "dmg");
  assert.equal(installerKindFor(asset("Octop.exe", "exe")), "exe");
  assert.equal(installerKindFor(asset("Octop.AppImage", ".AppImage")), "appimage");
  assert.equal(installerKindFor(asset("Octop.deb", "deb")), "deb");
  assert.equal(installerKindFor(asset("Octop.pkg", "pkg")), "pkg");
  assert.equal(installerKindFor(asset("Octop.msi", "msi")), "msi");
});

test("installerKindFor falls back to the file name, then refuses", () => {
  assert.equal(installerKindFor(asset("Octop-1.0.3-arm64.DMG", "")), "dmg");
  assert.equal(installerKindFor(asset("Octop-1.0.3-arm64.zip", "")), "unsupported");
  assert.equal(installerKindFor(asset("Octop", "")), "unsupported");
  assert.equal(isSupportedKind("unsupported"), false);
});

test("downloadFilename never escapes the update directory", () => {
  assert.equal(
    downloadFilename(asset("Octop-1.0.3-arm64.dmg", "dmg"), "v1.0.3"),
    "Octop-1.0.3-arm64.dmg",
  );
  // Path components from a remote manifest are stripped.
  assert.equal(downloadFilename(asset("../../evil.dmg", "dmg"), "v1.0.3"), "evil.dmg");
  assert.equal(downloadFilename(asset("a/b/c.exe", "exe"), "v1.0.3"), "c.exe");
  assert.equal(downloadFilename(asset("..\\..\\evil.exe", "exe"), "v1.0.3"), "evil.exe");
  // Shell-significant characters collapse into a single separator.
  assert.equal(downloadFilename(asset("Oct; rm -rf ~ .dmg", "dmg"), "v1.0.3"), "Oct-rm--rf-.dmg");
  // Empty name → version-based fallback that still carries the extension.
  assert.equal(downloadFilename(asset("", "dmg"), "v1.0.3"), "Octop-v1.0.3.dmg");
});

test("planInstall keeps the shell-selected url and kind", () => {
  const plan = planInstall({
    tag: "v1.0.3",
    asset: asset("Octop-1.0.3-arm64.dmg", "dmg"),
    releasesUrl: "https://github.com/x/releases",
  });
  assert.deepEqual(plan, {
    kind: "dmg",
    url: "https://download.octop.cloud/x",
    filename: "Octop-1.0.3-arm64.dmg",
  });
});

const selected = {
  tag: "v1.0.3",
  asset: asset("Octop-1.0.3-arm64.dmg", "dmg"),
  releasesUrl: "https://github.com/x/releases",
};

function hooks(overrides: Partial<InstallHooks> = {}) {
  const calls: string[] = [];
  const base: InstallHooks = {
    download: async () => {
      calls.push("download");
      return "/tmp/octop-update/Octop-1.0.3-arm64.dmg";
    },
    verify: async () => {
      calls.push("verify");
      return true;
    },
    stopSidecar: async () => {
      calls.push("stop");
      return { clean: true, exitCode: 0 };
    },
    handOff: async () => {
      calls.push("handoff");
    },
  };
  return { calls, hooks: { ...base, ...overrides } };
}

test("installUpdate runs consent → download → verify → clean exit → handoff", async () => {
  const { calls, hooks: h } = hooks();
  const outcome = await installUpdate(selected, h);
  assert.deepEqual(outcome, { ok: true, path: "/tmp/octop-update/Octop-1.0.3-arm64.dmg" });
  assert.deepEqual(calls, ["download", "verify", "stop", "handoff"]);
});

test("unsupported asset is refused before anything is downloaded", async () => {
  const { calls, hooks: h } = hooks();
  const outcome = await installUpdate(
    { ...selected, asset: asset("Octop-1.0.3-arm64.zip", "zip") },
    h,
  );
  assert.equal(outcome.ok, false);
  assert.equal(outcome.ok === false && outcome.reason, "unsupported");
  assert.deepEqual(calls, []);
});

test("download failure aborts before Python is touched", async () => {
  const { calls, hooks: h } = hooks({
    download: async () => {
      throw new Error("HTTP 404");
    },
  });
  const outcome = await installUpdate(selected, h);
  assert.equal(outcome.ok === false && outcome.reason, "download");
  assert.deepEqual(calls, []);
});

test("an asset url outside the download host is refused", async () => {
  const { calls, hooks: h } = hooks();
  const outcome = await installUpdate(
    { ...selected, asset: { ...selected.asset, url: "https://evil.example/Octop.dmg" } },
    h,
  );
  assert.equal(outcome.ok === false && outcome.reason, "untrusted-url");
  assert.deepEqual(calls, []);
});

test("failed verification aborts before Python is touched", async () => {
  const { calls, hooks: h } = hooks({ verify: async () => false });
  const outcome = await installUpdate(selected, h);
  assert.equal(outcome.ok === false && outcome.reason, "verify");
  assert.deepEqual(calls, ["download"]);
});

test("a sidecar that did not exit 0 cancels the install", async () => {
  const { calls, hooks: h } = hooks({ stopSidecar: async () => ({ clean: false, exitCode: null }) });
  const outcome = await installUpdate(selected, h);
  assert.equal(outcome.ok === false && outcome.reason, "unclean-exit");
  // Nothing was handed to the installer.
  assert.deepEqual(calls, ["download", "verify"]);
});

test("non-zero exit code is treated as unclean", async () => {
  const { hooks: h } = hooks({ stopSidecar: async () => ({ clean: false, exitCode: 1 }) });
  const outcome = await installUpdate(selected, h);
  assert.equal(outcome.ok === false && outcome.reason, "unclean-exit");
});

test("handoff failure restarts the backend instead of leaving it dead", async () => {
  let restarted = 0;
  const { hooks: h } = hooks({
    handOff: async () => {
      throw new Error("LaunchServices refused the file");
    },
    onHandOffFailure: async () => {
      restarted += 1;
    },
  });
  const outcome = await installUpdate(selected, h);
  assert.equal(outcome.ok === false && outcome.reason, "handoff");
  assert.equal(restarted, 1);
});
