/**
 * Shell-owned update installation (§6.3).
 *
 * The renderer can only ask the main process to OPEN the confirmation dialog;
 * it never supplies a URL and never authorizes an install. Every value used
 * here comes from the shell's own manifest selection, so a hostile renderer
 * cannot redirect the download to another host.
 *
 * Order is fixed and must not be reordered:
 *   consent → download → verify → Python clean exit (code 0) → hand off to the
 *   OS installer. A dirty sidecar exit cancels the install instead of replacing
 *   files under a live Python process.
 */

import type { SidecarExit } from "../supervisor/sidecar";
import { isValidAssetUrl, type DownloadAsset, type SelectedRelease } from "./update-coordinator";

export type InstallerKind = "dmg" | "pkg" | "exe" | "msi" | "appimage" | "deb" | "unsupported";

const EXTENSION_KINDS: Readonly<Record<string, InstallerKind>> = {
  dmg: "dmg",
  pkg: "pkg",
  exe: "exe",
  msi: "msi",
  appimage: "appimage",
  deb: "deb",
};

/** Extensions the shell is willing to open. Everything else is refused. */
const SUPPORTED_KINDS: readonly InstallerKind[] = ["dmg", "pkg", "exe", "msi", "appimage", "deb"];

function normalizeExt(ext: string): string {
  return ext.trim().replace(/^\.+/, "").toLowerCase();
}

function nameExt(name: string): string {
  const match = name.trim().toLowerCase().match(/\.([a-z0-9]+)$/);
  return match?.[1] ?? "";
}

/**
 * Resolve the installer type from the manifest asset. ``ext`` wins; the file
 * name is only a fallback for manifests that leave ``ext`` empty.
 */
export function installerKindFor(asset: DownloadAsset): InstallerKind {
  const fromExt = EXTENSION_KINDS[normalizeExt(asset.ext)];
  if (fromExt) return fromExt;
  return EXTENSION_KINDS[nameExt(asset.name)] ?? "unsupported";
}

export function isSupportedKind(kind: InstallerKind): boolean {
  return SUPPORTED_KINDS.includes(kind);
}

/**
 * Local file name for the download. The name arrives from a remote manifest, so
 * every path separator and shell-significant character is stripped: the file can
 * only ever land directly inside the shell's update directory.
 */
export function downloadFilename(asset: DownloadAsset, tag: string): string {
  const ext = normalizeExt(asset.ext) || nameExt(asset.name) || "bin";
  const withoutDir = (asset.name.trim().split(/[\\/]/).pop() ?? "").replace(/\.[A-Za-z0-9]+$/, "");
  const safeStem =
    withoutDir.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^[-.]+/, "") ||
    `Octop-${tag.replace(/[^A-Za-z0-9._-]+/g, "-")}`;
  return `${safeStem}.${ext}`;
}

export interface InstallPlan {
  kind: InstallerKind;
  url: string;
  filename: string;
}

export function planInstall(selected: SelectedRelease): InstallPlan {
  return {
    kind: installerKindFor(selected.asset),
    url: selected.asset.url,
    filename: downloadFilename(selected.asset, selected.tag),
  };
}

/** Outcome of asking the sidecar to shut down (§3.4). */
export type { SidecarExit };

export interface InstallHooks {
  /** Download the plan's URL, returning the local path of the finished file. */
  download(plan: InstallPlan): Promise<string>;
  /** Integrity check on the downloaded file; ``false`` aborts the install. */
  verify(path: string): Promise<boolean>;
  /** Ask Python to exit; must resolve within the shell's grace window. */
  stopSidecar(): Promise<SidecarExit>;
  /** Open the OS installer / mounted image for the given file. */
  handOff(kind: InstallerKind, path: string): Promise<void>;
  /** Install opened but failed: bring the shell's own backend back up. */
  onHandOffFailure?(): Promise<void>;
}

export type InstallFailureReason =
  | "unsupported"
  | "untrusted-url"
  | "download"
  | "verify"
  | "unclean-exit"
  | "handoff";

export type InstallOutcome =
  | { ok: true; path: string }
  | { ok: false; reason: InstallFailureReason; message: string };

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export async function installUpdate(
  selected: SelectedRelease,
  hooks: InstallHooks,
): Promise<InstallOutcome> {
  const plan = planInstall(selected);
  if (!isSupportedKind(plan.kind)) {
    return {
      ok: false,
      reason: "unsupported",
      message: `不支持的安装包类型：${selected.asset.ext || selected.asset.name}`,
    };
  }
  // Defence in depth: `selectRelease` already filtered on this, but the check
  // lives here too so no future caller can download from an arbitrary host.
  if (!isValidAssetUrl(plan.url)) {
    return { ok: false, reason: "untrusted-url", message: "安装包地址不在允许的下载主机范围内。" };
  }

  let path: string;
  try {
    path = await hooks.download(plan);
  } catch (err) {
    return { ok: false, reason: "download", message: messageOf(err) };
  }

  try {
    if (!(await hooks.verify(path))) {
      return { ok: false, reason: "verify", message: "安装包校验失败，已取消安装。" };
    }
  } catch (err) {
    return { ok: false, reason: "verify", message: messageOf(err) };
  }

  const exit = await hooks.stopSidecar();
  if (!exit.clean) {
    return {
      ok: false,
      reason: "unclean-exit",
      message: `Python 后端未能在宽限期内干净退出（退出码 ${exit.exitCode ?? "无"}），已取消安装。`,
    };
  }

  try {
    await hooks.handOff(plan.kind, path);
  } catch (err) {
    // Files were never touched, so the shell can keep running: restart Python.
    await hooks.onHandOffFailure?.();
    return { ok: false, reason: "handoff", message: messageOf(err) };
  }

  return { ok: true, path };
}
