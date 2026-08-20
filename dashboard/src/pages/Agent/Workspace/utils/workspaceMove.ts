/** Resolve the destination directory when dragging a workspace tree node. */

export function parentDir(path: string): string {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.length ? `/${parts.join("/")}` : "/";
}

export function joinWorkspacePath(dir: string, name: string): string {
  const base = dir.endsWith("/") ? dir.slice(0, -1) : dir;
  if (!base || base === "/") return `/${name}`;
  return `${base}/${name}`;
}

export function isDescendantPath(ancestor: string, candidate: string): boolean {
  const a = ancestor.replace(/\/$/, "") || "/";
  const c = candidate.replace(/\/$/, "") || "/";
  return c === a || c.startsWith(`${a}/`);
}

export function resolveWorkspaceMoveDest(opts: {
  dragPath: string;
  dropPath: string;
  dropIsDir: boolean;
  dropToGap: boolean;
}): string | null {
  const dragPath = opts.dragPath;
  const dropPath = opts.dropPath;
  if (!dragPath || !dropPath) return null;
  const destDir =
    opts.dropIsDir && !opts.dropToGap ? dropPath : parentDir(dropPath);
  if (isDescendantPath(dragPath, destDir) && destDir !== dragPath) {
    return null;
  }
  const basename = dragPath.split("/").filter(Boolean).pop();
  if (!basename) return null;
  const dest = joinWorkspacePath(destDir, basename);
  if (dest === dragPath) return null;
  return dest;
}
