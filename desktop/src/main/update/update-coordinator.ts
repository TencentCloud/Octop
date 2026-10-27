/**
 * Shell update coordinator (§6.1). This module only *selects* a release from the
 * manifest; the download lives in `download.ts` and the install hand-off in
 * `installer.ts`. Neither is reachable from the renderer — the preload bridge
 * exposes exactly one call, `openUpdateConfirmation()`, which takes no arguments.
 */

import { isNewer, parseVersion } from "../supervisor/version";

export interface DownloadAsset {
  name: string;
  ext: string;
  url: string;
}

export interface ChannelRelease {
  tag: string;
  releasesUrl: string;
  assets: Partial<Record<"mac_arm" | "mac_intel" | "win_x64" | "win_arm", DownloadAsset>>;
}

export interface DownloadManifest {
  client: { stable?: ChannelRelease; beta?: ChannelRelease };
}

export type PlatformKey = "mac_arm" | "mac_intel" | "win_x64" | "win_arm";

export function platformAssetKey(platform: NodeJS.Platform, arch: string): PlatformKey | null {
  if (platform === "darwin") return arch === "arm64" ? "mac_arm" : "mac_intel";
  if (platform === "win32") return arch === "arm64" ? "win_arm" : "win_x64";
  return null; // Linux is not in the current manifest keys (§6.1).
}

export interface SelectedRelease {
  tag: string;
  asset: DownloadAsset;
  releasesUrl: string;
}

const ALLOWED_DOWNLOAD_HOST = "download.octop.cloud";

/** Only ``https`` assets from the fixed download host are accepted. */
export function isValidAssetUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname === ALLOWED_DOWNLOAD_HOST;
  } catch {
    return false;
  }
}

/**
 * Pick the highest eligible release from the manifest (§6.1).
 * - stableOnly: only ``stable`` is a candidate.
 * - Drop candidates not newer than ``currentVersion`` and without a local asset.
 * - Never offer a downgrade when the installed version is already a higher beta.
 */
export function selectRelease(
  manifest: DownloadManifest,
  currentVersion: string,
  platform: PlatformKey | null,
  stableOnly: boolean,
): SelectedRelease | null {
  if (platform === null) return null;
  const candidates: ChannelRelease[] = [];
  if (manifest.client.stable) candidates.push(manifest.client.stable);
  if (!stableOnly && manifest.client.beta) candidates.push(manifest.client.beta);

  const eligible = candidates.filter((release) => {
    const asset = release.assets[platform];
    if (!asset || !isValidAssetUrl(asset.url)) return false;
    let tag = release.tag;
    if (!parseVersion(tag)) return false;
    if (!isNewer(tag, currentVersion)) return false;
    return true;
  });

  eligible.sort((a, b) => {
    // Both parse (filtered above); higher version first.
    const aTag = a.tag.startsWith("v") ? a.tag.slice(1) : a.tag;
    const bTag = b.tag.startsWith("v") ? b.tag.slice(1) : b.tag;
    return parseVersion(bTag)! > parseVersion(aTag)! ? 1 : -1;
  });

  const best = eligible[0];
  if (!best) return null;
  const asset = best.assets[platform]!;
  return { tag: best.tag, asset, releasesUrl: best.releasesUrl };
}
