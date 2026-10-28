/**
 * Product version resolution.
 *
 * The shell, the bundled Dashboard assets and the green Python runtime ship as
 * one release, so there is exactly one product version. `package.json` carries
 * a local placeholder and would go stale the moment someone bumps `pyproject`,
 * so it is only the last resort: the bundled portable manifest is authoritative
 * in a packaged build, and the dev runtime's `version.json` covers `pnpm dev`.
 *
 * The resolved value feeds three things, all of which break on a wrong number:
 * the update release selection (§6.1), the expected `Octop-portable-*.zip`
 * filename (§2.3), and the copy in the install confirmation dialog.
 */

export interface AppVersionSources {
  /** Version from the bundled `resources/portable/portable-version.json`. */
  readBundled: () => Promise<string | null>;
  /** Version from the dev runtime's `version.json` (`OCTOP_PORTABLE_DIR`). */
  readDevRuntime: () => Promise<string | null>;
  /** Last resort: `app.getVersion()` from `package.json`. */
  readPackage: () => string;
}

/**
 * Resolve the product version by trying each source in order. A source that
 * throws, returns null, or returns a blank string falls through to the next one
 * — never to an empty version, because ``""`` would make every release look
 * newer than the current install.
 */
export async function resolveAppVersion(sources: AppVersionSources): Promise<string> {
  const readers = [sources.readBundled, sources.readDevRuntime];
  for (const read of readers) {
    try {
      const version = (await read())?.trim();
      if (version) return version;
    } catch {
      // Missing manifest / unreadable dev runtime: try the next source.
    }
  }
  return sources.readPackage().trim();
}
