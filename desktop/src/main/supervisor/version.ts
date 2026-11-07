/**
 * Version ordering shared by the runtime version guard (§2.3) and the shell
 * update channel selection (§6.1).
 *
 * Ordering matches the architecture doc exactly:
 *   - strip a leading ``v`` before comparing (``v1.0.2`` == ``1.0.2``)
 *   - ``1.0.3`` > ``1.0.3b1`` (release beats its own pre-release)
 *   - ``1.0.3b1`` > ``1.0.2`` (pre-release of a higher triple wins)
 *   - versions that cannot be ordered are reported as unparseable so callers
 *     can treat the bundle as corrupt rather than guessing.
 */

export interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  /** Trailing pre-release segment (e.g. ``"b1"``, ``"beta.4"``), or ``null``. */
  pre: string | null;
}

const VERSION_RE = /^v?(\d+)\.(\d+)\.(\d+)(.*)$/;

export function parseVersion(raw: string): ParsedVersion | null {
  const m = VERSION_RE.exec(raw.trim());
  if (!m) return null;
  const major = Number(m[1]);
  const minor = Number(m[2]);
  const patch = Number(m[3]);
  if (!Number.isSafeInteger(major) || !Number.isSafeInteger(minor) || !Number.isSafeInteger(patch)) {
    return null;
  }
  const pre = m[4] ? m[4].replace(/^[-._]/, "") : "";
  return { major, minor, patch, pre: pre === "" ? null : pre };
}

/**
 * Compare two raw version strings.
 * @returns negative when ``a < b``, zero when equal, positive when ``a > b``.
 * @throws when either side cannot be parsed — ordering must be total here.
 */
export function compareVersions(a: string, b: string): number {
  const pa = parseVersion(a);
  const pb = parseVersion(b);
  if (!pa || !pb) {
    throw new Error(`cannot compare versions: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
  }
  for (const key of ["major", "minor", "patch"] as const) {
    if (pa[key] !== pb[key]) return pa[key] - pb[key];
  }
  // Same numeric triple: a release (no pre) is newer than any pre-release.
  if (pa.pre === null && pb.pre === null) return 0;
  if (pa.pre === null) return 1;
  if (pb.pre === null) return -1;
  // Two pre-releases of the same triple: fall back to a simple case-insensitive
  // ordinal compare so ``1.0.3b2 > 1.0.3b1`` and both are "ordered".
  const la = pa.pre.toLowerCase();
  const lb = pb.pre.toLowerCase();
  return la < lb ? -1 : la > lb ? 1 : 0;
}

/** True when ``candidate`` is strictly newer than ``current``. */
export function isNewer(candidate: string, current: string): boolean {
  return compareVersions(candidate, current) > 0;
}
