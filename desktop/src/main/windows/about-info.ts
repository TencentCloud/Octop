/**
 * About-box body. Field names match the usual desktop about list
 * (Version, Commit, Date, Electron, Chromium, Node.js, V8, OS).
 */

export type WindowsInstallScope = "user" | "system";

export interface AboutFacts {
  version: string;
  /** Per-user vs per-machine install. Dev builds pass null. */
  setup: WindowsInstallScope | null;
  commit: string;
  /** UTC `YYYY-MM-DDTHH:mm:ssZ`, or empty when unknown. */
  date: string;
  electron: string;
  chromium: string;
  node: string;
  v8: string;
  os: string;
}

export function windowsInstallScope(execPath: string): WindowsInstallScope | null {
  const norm = execPath.replaceAll("/", "\\").toLowerCase();
  if (norm.includes("\\program files")) return "system";
  if (norm.endsWith("\\electron.exe") || norm.includes("\\node_modules\\")) return null;
  return "user";
}

/** `Windows_NT x64 10.0.26300`. */
export function formatAboutOs(type: string, arch: string, release: string): string {
  return `${type} ${arch} ${release}`;
}

/** Git `%cI` (with an offset) becomes UTC without milliseconds. */
export function formatAboutDate(iso: string): string {
  const trimmed = iso.trim();
  if (!trimmed) return "";
  const parsed = Date.parse(trimmed);
  if (Number.isNaN(parsed)) return trimmed;
  return new Date(parsed).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function formatAboutDetail(facts: AboutFacts): string {
  const version =
    facts.setup === null ? facts.version.trim() : `${facts.version.trim()} (${facts.setup} setup)`;
  const lines = [
    pair("Version", version),
    pair("Commit", facts.commit),
    pair("Date", facts.date),
    pair("Electron", facts.electron),
    pair("Chromium", facts.chromium),
    pair("Node.js", facts.node),
    pair("V8", facts.v8),
    pair("OS", facts.os),
  ];
  return lines.filter((line): line is string => line !== null).join("\n");
}

function pair(label: string, value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? `${label}: ${trimmed}` : null;
}

/**
 * Prefer a live git checkout. A packaged build has no `.git`, so the values
 * baked in at `electron-vite` time are the fallback.
 */
export function resolveGitStamp(
  run: (args: readonly string[]) => string | null,
  baked: { commit?: string; date?: string } = {},
): { commit: string; date: string } {
  const commit = run(["rev-parse", "HEAD"])?.trim() || baked.commit?.trim() || "";
  const rawDate = run(["log", "-1", "--format=%cI"])?.trim() || baked.date?.trim() || "";
  return { commit, date: formatAboutDate(rawDate) };
}
