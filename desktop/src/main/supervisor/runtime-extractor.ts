import { existsSync, mkdirSync, renameSync, rmSync, symlinkSync } from "node:fs";
import { isAbsolute, join, normalize } from "node:path";
import AdmZip from "adm-zip";

/** Unix file-type mask and the symlink type stored in a zip external attribute. */
const S_IFMT = 0o170000;
const S_IFLNK = 0o120000;

/**
 * Expanded runtimes shipped beside the app, checked before any first-launch unzip.
 * Windows NSIS writes ``resources/sidecar``. macOS and Linux packaging copy
 * the assembled tree into ``resources/portable`` before the app is packed.
 * A directory that only holds the zip is not an installed runtime.
 */
const INSTALLED_RUNTIME_DIRS = ["sidecar", "portable"] as const;

export function runtimeInterpreterRelative(platform: string): string {
  return join("runtime", platform === "win32" ? "python.exe" : "bin/python3");
}

/** Zip name the shell accepts: ``Octop-portable-<plat>-<version>.zip``. */
export function portableZipName(platformTag: string, version: string): string {
  return `Octop-portable-${platformTag}-${version}.zip`;
}

/** Dashboard files inside the portable tree. The shell serves this copy. */
export function bundledDashboardDir(portableDir: string): string {
  return join(portableDir, "packages", "octop", "dashboard");
}

export function installedRuntimeDir(
  resourcesRoot: string,
  platform: string,
  exists: (path: string) => boolean,
): string | null {
  const interpreter = runtimeInterpreterRelative(platform);
  for (const name of INSTALLED_RUNTIME_DIRS) {
    const dir = join(resourcesRoot, name);
    if (exists(join(dir, "launch.py")) && exists(join(dir, interpreter))) return dir;
  }
  return null;
}

/**
 * Runtime extraction decision and safe atomic unzip for the portable Python
 * runtime (§2.2 / §2.3). The extracted runtime lives under
 * ``<OCTOP_HOME>/portable`` and is replaced atomically, never in place, so a
 * failed extraction never leaves a half-written runtime that claims a version.
 */

export type RuntimeDecision =
  | { action: "extract"; reason: "first-run" | "missing" }
  | { action: "skip"; reason: "up-to-date" }
  | { action: "replace"; reason: "corrupt" | "older" }
  | { action: "stop"; reason: "local-newer"; localVersion: string };

export interface BundledPortable {
  version: string;
  sha256: string;
}

export interface LocalRuntime {
  /** Parsed ``version`` from ``<OCTOP_HOME>/portable/version.json``. */
  version: string | null;
  /** True when the interpreter binary exists at the expected location. */
  interpreterExists: boolean;
}

export function classifyRuntime(
  bundled: BundledPortable,
  local: LocalRuntime,
  compare: (a: string, b: string) => number,
): RuntimeDecision {
  // 1. No local file yet → first run, extract.
  if (local.version === null && !local.interpreterExists) {
    return { action: "extract", reason: "first-run" };
  }
  // 2. Local file exists but version is unparseable/missing → treat as corrupt.
  if (local.version === null) {
    return { action: "replace", reason: "corrupt" };
  }
  const cmp = compare(local.version, bundled.version);
  if (cmp === 0) {
    // 3. Same version: skip if the interpreter is intact, else replace.
    return local.interpreterExists
      ? { action: "skip", reason: "up-to-date" }
      : { action: "replace", reason: "corrupt" };
  }
  // 4. Local lower than bundled → replace with the bundled runtime.
  if (cmp < 0) return { action: "replace", reason: "older" };
  // 5. Local higher than bundled → manual downgrade; stop before spawning Python.
  return { action: "stop", reason: "local-newer", localVersion: local.version };
}

/** Reject entries that would escape the destination (zip-slip) or are absolute. */
export function isSafeEntryPath(entryPath: string): boolean {
  if (entryPath.includes("\0")) return false;
  const normalized = normalize(entryPath);
  if (normalized === ".." || normalized.startsWith("..")) return false;
  if (isAbsolute(normalized)) return false;
  // Any remaining ``..`` component (e.g. ``a/../../b`` on the host separator)
  // still escapes — reject it outright.
  return !normalized.split(/[\\/]/).includes("..");
}

/** Return the single top-level directory name shared by every entry, or null. */
export function detectSingleRoot(entryNames: string[]): string | null {
  const tops = new Set<string>();
  for (const name of entryNames) {
    const norm = name.replace(/\\/g, "/").replace(/^\/+/, "");
    if (!norm) continue;
    const top = norm.split("/")[0];
    if (top) tops.add(top);
    if (tops.size > 1) return null;
  }
  return tops.size === 1 ? ([...tops][0] ?? null) : null;
}

/** High 16 bits of a zip external attribute. ``0`` when the archive stored none. */
function unixMode(attr: number): number {
  return (attr >>> 16) & 0xffff;
}

/**
 * Symlink targets in the portable runtime are same-directory names (`python3` →
 * `python3.12`). Absolute targets and any `..` component would escape the tree.
 */
export function isSafeSymlinkTarget(target: string): boolean {
  if (target.length === 0 || target.includes("\0") || target.includes("\n") || target.includes("\r")) {
    return false;
  }
  if (isAbsolute(target) || /^[a-zA-Z]:[\\/]/.test(target)) return false;
  return !normalize(target).split(/[\\/]/).includes("..");
}

/**
 * `adm-zip` writes every entry as a regular file and only restores the low 9
 * permission bits. Info-ZIP stores `bin/python3` as a symlink whose payload is
 * the target name; without this step spawn fails with EACCES on that text file.
 */
function restoreSymlinks(zip: AdmZip, staging: string): void {
  for (const entry of zip.getEntries()) {
    if ((unixMode(entry.header.attr) & S_IFMT) !== S_IFLNK) continue;
    const rel = entry.entryName.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
    const dest = join(staging, rel);
    const target = entry.getData().toString("utf8");
    if (!isSafeSymlinkTarget(target)) {
      throw new Error(
        `unsafe symlink in portable archive: ${JSON.stringify(entry.entryName)} -> ${JSON.stringify(target)}`,
      );
    }
    rmSync(dest, { force: true });
    symlinkSync(target, dest);
  }
}

/**
 * Extract the green portable zip into ``destDir`` atomically (§2.2).
 * The archive wraps everything in a single ``Octop-<plat>/`` folder, so that
 * wrapper is stripped before the swap.
 */
export function extractPortableZip(zipPath: string, destDir: string): void {
  const zip = new AdmZip(zipPath);
  const entries = zip.getEntries();
  for (const entry of entries) {
    if (!isSafeEntryPath(entry.entryName)) {
      throw new Error(`unsafe entry in portable archive: ${JSON.stringify(entry.entryName)}`);
    }
  }

  const staging = `${destDir}.staging`;
  const previous = `${destDir}.previous`;
  rmSync(staging, { recursive: true, force: true });
  mkdirSync(staging, { recursive: true });
  // Third argument keeps the Unix mode (python3.12 is 0755, not the 0666 default).
  zip.extractAllTo(staging, true, true);
  restoreSymlinks(zip, staging);

  // Strip the single top-level wrapper dir unless launch.py sits at the root.
  let src = staging;
  const root = detectSingleRoot(entries.map((e) => e.entryName));
  if (root && !existsSync(join(staging, "launch.py"))) {
    const inner = join(staging, root);
    if (existsSync(inner)) src = inner;
  }

  if (existsSync(destDir)) {
    rmSync(previous, { recursive: true, force: true });
    renameSync(destDir, previous);
  }
  renameSync(src, destDir);
  rmSync(previous, { recursive: true, force: true });
  rmSync(staging, { recursive: true, force: true });
}
