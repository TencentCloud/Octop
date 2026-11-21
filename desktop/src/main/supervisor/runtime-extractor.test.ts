import assert from "node:assert/strict";
import { lstatSync, mkdtempSync, readlinkSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import AdmZip from "adm-zip";

import {
  bundledDashboardDir,
  portableZipName,
  classifyRuntime,
  extractPortableZip,
  installedRuntimeDir,
  isSafeSymlinkTarget,
} from "./runtime-extractor";
import { compareVersions } from "./version";

const posixOnly = process.platform === "win32" ? { skip: "Unix symlink and mode bits" } : {};

const cmp = compareVersions;

test("classifyRuntime: first run extracts", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: null, interpreterExists: false },
    cmp,
  );
  assert.deepEqual(d, { action: "extract", reason: "first-run" });
});

test("classifyRuntime: unparseable local version replaces", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: null, interpreterExists: true },
    cmp,
  );
  assert.equal(d.action, "replace");
});

test("classifyRuntime: same version with interpreter skips", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: "1.0.2", interpreterExists: true },
    cmp,
  );
  assert.deepEqual(d, { action: "skip", reason: "up-to-date" });
});

test("classifyRuntime: same version missing interpreter replaces", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: "1.0.2", interpreterExists: false },
    cmp,
  );
  assert.deepEqual(d, { action: "replace", reason: "corrupt" });
});

test("classifyRuntime: local lower replaces", () => {
  const d = classifyRuntime(
    { version: "1.0.3", sha256: "x" },
    { version: "1.0.2", interpreterExists: true },
    cmp,
  );
  assert.deepEqual(d, { action: "replace", reason: "older" });
});

test("isSafeSymlinkTarget allows a same-directory name", () => {
  assert.equal(isSafeSymlinkTarget("python3.12"), true);
  assert.equal(isSafeSymlinkTarget("../python3.12"), false);
  assert.equal(isSafeSymlinkTarget("/usr/bin/python3"), false);
  assert.equal(isSafeSymlinkTarget(""), false);
});

/** Build a zip whose external attributes carry a full Unix mode, including symlink type. */
function writeModeZip(dir: string, entries: { name: string; data: string; mode: number }[]): string {
  const zip = new AdmZip();
  for (const entry of entries) {
    const added = zip.addFile(entry.name, Buffer.from(entry.data));
    added.attr = (entry.mode << 16) >>> 0;
  }
  const path = join(dir, "portable.zip");
  zip.writeZip(path);
  return path;
}

test("extractPortableZip restores the python3 symlink and the executable bit", posixOnly, () => {
  const dir = mkdtempSync(join(tmpdir(), "octop-extract-"));
  try {
    const zipPath = writeModeZip(dir, [
      { name: "Octop-darwin-arm64/launch.py", data: "print(1)\n", mode: 0o100644 },
      { name: "Octop-darwin-arm64/runtime/bin/python3.12", data: "#!/bin/sh\n", mode: 0o100755 },
      { name: "Octop-darwin-arm64/runtime/bin/python3", data: "python3.12", mode: 0o120755 },
    ]);
    const dest = join(dir, "portable");
    extractPortableZip(zipPath, dest);
    const link = join(dest, "runtime/bin/python3");
    assert.equal(lstatSync(link).isSymbolicLink(), true);
    assert.equal(readlinkSync(link), "python3.12");
    assert.equal(statSync(join(dest, "runtime/bin/python3.12")).mode & 0o777, 0o755);
    assert.equal(statSync(join(dest, "launch.py")).mode & 0o777, 0o644);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("extractPortableZip rejects a symlink that escapes the tree", () => {
  const dir = mkdtempSync(join(tmpdir(), "octop-extract-"));
  try {
    const zipPath = writeModeZip(dir, [
      { name: "Octop-darwin-arm64/launch.py", data: "print(1)\n", mode: 0o100644 },
      { name: "Octop-darwin-arm64/runtime/bin/python3", data: "../../outside", mode: 0o120755 },
    ]);
    const dest = join(dir, "portable");
    assert.throws(() => extractPortableZip(zipPath, dest), /unsafe symlink/);
    assert.equal(statExists(dest), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

function statExists(path: string): boolean {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

test("portableZipName is the unsuffixed release zip", () => {
  assert.equal(
    portableZipName("windows-amd64", "1.0.3b4"),
    "Octop-portable-windows-amd64-1.0.3b4.zip",
  );
});

test("bundledDashboardDir is the copy inside the portable tree", () => {
  assert.equal(
    bundledDashboardDir(join("resources", "portable")),
    join("resources", "portable", "packages", "octop", "dashboard"),
  );
});

test("installedRuntimeDir prefers the Windows install expansion", () => {
  const root = join("resources");
  const present = new Set([
    join(root, "sidecar", "launch.py"),
    join(root, "sidecar", "runtime", "python.exe"),
    join(root, "portable", "launch.py"),
  ]);
  assert.equal(
    installedRuntimeDir(root, "win32", (path) => present.has(path)),
    join(root, "sidecar"),
  );
});

test("installedRuntimeDir uses the expanded macOS tree", () => {
  const root = join("resources");
  const present = new Set([
    join(root, "portable", "launch.py"),
    join(root, "portable", "runtime", "bin", "python3"),
  ]);
  assert.equal(
    installedRuntimeDir(root, "darwin", (path) => present.has(path)),
    join(root, "portable"),
  );
});

test("installedRuntimeDir ignores a directory that only contains the zip", () => {
  const root = join("resources");
  const present = new Set([join(root, "portable", "Octop-portable-linux-amd64-1.0.3.zip")]);
  assert.equal(installedRuntimeDir(root, "linux", (path) => present.has(path)), null);
});

test("classifyRuntime: local higher stops (manual downgrade)", () => {
  const d = classifyRuntime(
    { version: "1.0.2", sha256: "x" },
    { version: "1.0.3", interpreterExists: true },
    cmp,
  );
  assert.deepEqual(d, { action: "stop", reason: "local-newer", localVersion: "1.0.3" });
});
