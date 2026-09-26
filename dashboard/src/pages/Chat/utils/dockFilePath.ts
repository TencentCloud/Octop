/**
 * Normalize and identify dock file paths so list / tabs / message open
 * share one stable key.
 *
 * I/O URL construction lives in ``utils/workspaceIoPath.ts`` — dock only
 * canonicalizes for tab identity / dedupe.
 */

import {
  normalizeIoPath,
  toDockWorkspaceApiPath as toDockWorkspaceApiPathIo,
  toWorkspaceApiPath as toWorkspaceApiPathIo,
} from "../../../utils/workspaceIoPath";

export {
  isHostAbsolutePath,
  normalizeIoPath,
} from "../../../utils/workspaceIoPath";

/** Keep tool path shape: absolute stays absolute, relative stays relative. */
export const normalizeDockFilePath = normalizeIoPath;

/**
 * Collapse agent-home absolute paths (and truncated ``/.octop/agents/…``
 * extracts) to a workspace-relative path for stable list / tab identity.
 *
 * ``/home/wally/.octop/agents/main/generated/a.pptx``,
 * ``C:/Users/wally/.octop/agents/main/generated/a.pptx``, and
 * ``/.octop/agents/main/generated/a.pptx`` all become
 * ``generated/a.pptx``.
 *
 * Do **not** use this for download / file API paths — use
 * ``toDockWorkspaceApiPath`` so virtual ``root_dir`` failback still sees
 * the host-absolute form.
 */
export function canonicalizeDockFilePath(
  raw: string,
  agentId?: string | null,
): string {
  const normalized = normalizeDockFilePath(raw);
  if (!normalized) return "";
  // Windows drive paths → posix-ish for marker matching.
  let posix = normalized.replace(/\\/g, "/");
  if (/^[A-Za-z]:[^/]/.test(posix)) {
    posix = `${posix.slice(0, 2)}/${posix.slice(2)}`;
  }
  const lower = posix.toLowerCase();

  if (agentId) {
    const id = agentId.replace(/\\/g, "/");
    const idLower = id.toLowerCase();
    const markers = [`/.octop/agents/${idLower}/`, `.octop/agents/${idLower}/`];
    for (const marker of markers) {
      const idx = lower.lastIndexOf(marker);
      if (idx >= 0) {
        return posix.slice(idx + marker.length);
      }
    }
    const agentRoot = `/.octop/agents/${idLower}`;
    if (
      lower === agentRoot ||
      lower.endsWith(agentRoot) ||
      lower === agentRoot.slice(1) ||
      lower.endsWith(`.octop/agents/${idLower}`)
    ) {
      return "";
    }
  }

  const anyAgent = posix.match(/(?:^|\/)\.octop\/agents\/[^/]+\/(.+)$/i);
  if (anyAgent?.[1]) return anyAgent[1];

  if (posix === "/workspace") return "";
  // Only strip the virtual root ``/workspace/…`` — not host paths that happen
  // to contain a directory named ``workspace`` (e.g. ``/Users/me/workspace/a.pptx``).
  if (posix.startsWith("/workspace/")) {
    return posix.slice("/workspace/".length);
  }

  return posix;
}

/**
 * Workspace API path for dock download / open.
 * Host-absolute paths stay ``file://…`` (no agent-home collapse).
 */
export function toDockWorkspaceApiPath(
  raw: string,
  _agentId?: string | null,
): string {
  return toDockWorkspaceApiPathIo(raw);
}

/** @deprecated Prefer importing from ``utils/workspaceIoPath``. */
export const toWorkspaceApiPath = toWorkspaceApiPathIo;

/** Display basename for dock tab titles / list rows. */
export function dockFileBasename(path: string): string {
  const normalized = normalizeDockFilePath(path).replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
}

/** Stable tab id for an open file path (scoped by producer agent when set). */
export function dockFileTabId(path: string, agentId?: string | null): string {
  const key = canonicalizeDockFilePath(path, agentId);
  const aid = (agentId || "").trim();
  return aid ? `file:${aid}:${key}` : `file:${key}`;
}

export type DockFileRef = {
  path: string;
  agentId?: string;
};

/** Prefer a richer on-disk path for tree display after canonical dedupe. */
function preferDisplayPath(current: string, candidate: string): string {
  const a = current.replace(/\\/g, "/");
  const b = candidate.replace(/\\/g, "/");
  const score = (p: string) => {
    let s = p.length;
    if (p.startsWith("/") || /^[A-Za-z]:\//.test(p)) s += 1000;
    if (
      p.includes("/.octop/agents/") ||
      p.startsWith("/.octop/agents/") ||
      /(?:^|\/)\.octop\/agents\//i.test(p)
    ) {
      s += 500;
    }
    return s;
  };
  return score(b) > score(a) ? b : a;
}

/**
 * Deduplicate artifact paths for the dock file list, preferring absolute paths.
 * Entries are keyed by ``agentId + path`` so team rooms can list the same
 * relative path from multiple members.
 */
export function listDockFilePathsForTree(
  paths: Array<string | DockFileRef>,
  agentId?: string | null,
): DockFileRef[] {
  return dedupeDockFileRefs(paths, agentId);
}

/** @deprecated Prefer ``listDockFilePathsForTree`` (returns refs). */
export function dedupeDockFilePaths(
  paths: string[],
  agentId?: string | null,
): string[] {
  return dedupeDockFileRefs(paths, agentId).map((ref) => ref.path);
}

/** Deduplicate by producer agent + canonical workspace path. */
export function dedupeDockFileRefs(
  paths: Array<string | DockFileRef>,
  defaultAgentId?: string | null,
): DockFileRef[] {
  const bestByKey = new Map<string, DockFileRef>();
  const order: string[] = [];
  const fallback = (defaultAgentId || "").trim();
  for (const raw of paths) {
    const pathRaw = typeof raw === "string" ? raw : raw.path;
    const aid =
      (typeof raw === "string" ? fallback : raw.agentId?.trim() || fallback) ||
      "";
    const keyPath = canonicalizeDockFilePath(pathRaw, aid || defaultAgentId);
    if (!keyPath) continue;
    const display = normalizeDockFilePath(pathRaw) || keyPath;
    const key = `${aid}\0${keyPath}`;
    const prev = bestByKey.get(key);
    if (!prev) {
      bestByKey.set(key, {
        path: preferDisplayPath(keyPath, display),
        ...(aid ? { agentId: aid } : {}),
      });
      order.push(key);
      continue;
    }
    bestByKey.set(key, {
      path: preferDisplayPath(prev.path, display),
      ...(aid
        ? { agentId: aid }
        : prev.agentId
        ? { agentId: prev.agentId }
        : {}),
    });
  }
  return order.map((key) => bestByKey.get(key)!);
}

export type DockPathTreeNode = {
  /** Directory segment key (joined for collapsed chains) or file basename. */
  name: string;
  /** Full path for files; directory prefix for folders. */
  path: string;
  isDir: boolean;
  /** Producer agent for file leaves (team room multi-member artifacts). */
  agentId?: string;
  children: DockPathTreeNode[];
};

/**
 * Build a folder tree from flat paths, collapsing single-child directory
 * chains into ``a / b / c`` labels (PR “Files changed” style).
 */
export function buildDockPathTree(
  paths: Array<string | DockFileRef>,
  agentId?: string | null,
): DockPathTreeNode[] {
  type Trie = {
    name: string;
    path: string;
    isDir: boolean;
    agentId?: string;
    children: Map<string, Trie>;
  };

  const root: Trie = {
    name: "",
    path: "",
    isDir: true,
    children: new Map(),
  };

  for (const ref of listDockFilePathsForTree(paths, agentId)) {
    const raw = ref.path;
    const fileAgent = (ref.agentId || agentId || "").trim();
    const parts = raw.replace(/\\/g, "/").split("/").filter(Boolean);
    if (parts.length === 0) continue;
    // Preserve leading slash for absolute paths in the root segment join.
    const abs = raw.replace(/\\/g, "/").startsWith("/");
    let node = root;
    let acc = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      acc =
        acc === "" && abs ? `/${part}` : acc === "" ? part : `${acc}/${part}`;
      const childKey = isLast && fileAgent ? `${part}\0${fileAgent}` : part;
      let child = node.children.get(childKey);
      if (!child) {
        child = {
          name: part,
          path: acc,
          isDir: !isLast,
          ...(isLast && fileAgent ? { agentId: fileAgent } : {}),
          children: new Map(),
        };
        node.children.set(childKey, child);
      } else if (!isLast) {
        child.isDir = true;
      }
      node = child;
    }
  }

  function collapse(node: Trie): DockPathTreeNode {
    let cur = node;
    const names = [cur.name];
    while (
      cur.isDir &&
      cur.children.size === 1 &&
      [...cur.children.values()][0]?.isDir
    ) {
      cur = [...cur.children.values()][0];
      names.push(cur.name);
    }
    const children = [...cur.children.values()].map(collapse).sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    return {
      name: names.filter(Boolean).join(" / "),
      path: cur.path,
      isDir: cur.isDir || children.length > 0,
      ...(cur.agentId ? { agentId: cur.agentId } : {}),
      children,
    };
  }

  return [...root.children.values()].map(collapse).sort((a, b) => {
    if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

/** Collect every directory node path from a dock tree. */
export function collectDockFolderPaths(nodes: DockPathTreeNode[]): Set<string> {
  const out = new Set<string>();
  const walk = (list: DockPathTreeNode[]) => {
    for (const n of list) {
      if (!n.isDir) continue;
      out.add(n.path);
      walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

/**
 * Keep user-collapsed folders across tree updates; expand only newly
 * appearing directories. Drop paths that left the tree.
 */
export function mergeDockExpandedFolders(
  prevExpanded: Iterable<string>,
  folderPaths: Iterable<string>,
  previouslySeen: Iterable<string>,
): { expanded: Set<string>; seen: Set<string> } {
  const folders = new Set(folderPaths);
  const seenBefore = new Set(previouslySeen);
  const expanded = new Set<string>();
  for (const p of prevExpanded) {
    if (folders.has(p)) expanded.add(p);
  }
  for (const p of folders) {
    if (!seenBefore.has(p)) expanded.add(p);
  }
  return { expanded, seen: folders };
}
