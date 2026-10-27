import { existsSync, mkdirSync, renameSync, rmSync } from "node:fs";
import { isAbsolute, join, normalize } from "node:path";
import AdmZip from "adm-zip";

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
  zip.extractAllTo(staging, true);

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
