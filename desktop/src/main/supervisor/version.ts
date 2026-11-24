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
  return comparePre(pa.pre, pb.pre);
}

/** Pre-release stages in release order; PEP 440 and semver spellings mean the same stage. */
const PRE_STAGES: Record<string, number> = {
  dev: 0,
  a: 1,
  alpha: 1,
  b: 2,
  beta: 2,
  c: 3,
  rc: 3,
  pre: 3,
};

/**
 * Order two pre-release tags: by stage, then by number, so ``b8`` (Python
 * ``1.0.3b8``) equals ``beta.8`` (installer ``1.0.3-beta.8``) and ``beta.10``
 * is newer than ``beta.9``. Unknown shapes fall back to a case-insensitive
 * ordinal compare so the order stays total.
 */
function comparePre(a: string, b: string): number {
  const pa = /^([a-z]+)[-._]?(\d*)$/i.exec(a);
  const pb = /^([a-z]+)[-._]?(\d*)$/i.exec(b);
  const sa = pa ? PRE_STAGES[(pa[1] ?? "").toLowerCase()] : undefined;
  const sb = pb ? PRE_STAGES[(pb[1] ?? "").toLowerCase()] : undefined;
  if (pa && pb && sa !== undefined && sb !== undefined) {
    if (sa !== sb) return sa - sb;
    return Number(pa[2] || 0) - Number(pb[2] || 0);
  }
  const la = a.toLowerCase();
  const lb = b.toLowerCase();
  return la < lb ? -1 : la > lb ? 1 : 0;
}

/** True when ``candidate`` is strictly newer than ``current``. */
export function isNewer(candidate: string, current: string): boolean {
  return compareVersions(candidate, current) > 0;
}
