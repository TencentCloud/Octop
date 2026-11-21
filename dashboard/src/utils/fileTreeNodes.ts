/** Shared single-level file-tree helpers (workspace drawer + storage browse). */

import { workspaceEntryPath } from "./workspacePath";

export interface FileTreeInfo {
  path: string;
  is_dir?: boolean;
  size?: number;
  modified_at?: string;
}

export function nodeKey(path: string, isDir: boolean): string {
  return `${isDir ? "d" : "f"}:${path}`;
}

export function pathFromKey(key: string): { path: string; is_dir: boolean } {
  const sep = key.indexOf(":");
  return { is_dir: key[0] === "d", path: key.slice(sep + 1) };
}

export function normalizeTreePath(path: string): string {
  const full = workspaceEntryPath(path).replace(/\/+$/, "");
  return full || "/";
}

export function dedupeFileTreeInfos(
  infos: FileTreeInfo[],
  listedPath?: string,
): FileTreeInfo[] {
  const listed = listedPath ? normalizeTreePath(listedPath) : "";
  const merged = new Map<string, FileTreeInfo>();
  for (const info of infos) {
    const isDir = Boolean(info.is_dir) || String(info.path).endsWith("/");
    const fullPath = normalizeTreePath(info.path);
    if (fullPath === "/.") continue;
    if (listed && fullPath === listed) continue;
    const prev = merged.get(fullPath);
    if (prev) {
      if (isDir && !prev.is_dir) {
        merged.set(fullPath, { ...info, path: fullPath, is_dir: true });
      }
      continue;
    }
    merged.set(fullPath, { ...info, path: fullPath, is_dir: isDir });
  }
  return [...merged.values()].sort((a, b) => {
    const ad = a.is_dir ? 0 : 1;
    const bd = b.is_dir ? 0 : 1;
    if (ad !== bd) return ad - bd;
    const an = (
      normalizeTreePath(a.path).split("/").filter(Boolean).pop() || a.path
    ).toLowerCase();
    const bn = (
      normalizeTreePath(b.path).split("/").filter(Boolean).pop() || b.path
    ).toLowerCase();
    return an.localeCompare(bn);
  });
}
