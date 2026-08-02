/**
 * Normalize and identify dock file paths so list / tabs / message open
 * share one stable key.
 */

/** Keep tool path shape: absolute stays absolute, relative stays relative. */
export function normalizeDockFilePath(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  if (trimmed.toLowerCase().startsWith("file://")) {
    let abs = trimmed.slice("file://".length);
    if (abs.startsWith("//")) abs = abs.slice(1);
    return abs.startsWith("/") || /^[A-Za-z]:/.test(abs) ? abs : `/${abs}`;
  }
  return trimmed.replace(/\\/g, "/");
}

/**
 * Collapse agent-home absolute paths (and truncated ``/.octop/agents/…``
 * extracts) to a workspace-relative path for stable list / tab identity.
 *
 * ``/home/wally/.octop/agents/main/generated/a.pptx``,
 * ``C:/Users/wally/.octop/agents/main/generated/a.pptx``, and
 * ``/.octop/agents/main/generated/a.pptx`` all become
 * ``generated/a.pptx``.
 *
 * Related: ``toWorkspaceRelativePath`` in ``utils/workspacePath.ts`` (leading
 * ``/`` form for the workspace viewer). Keep dock keys slash-free so download
 * / tab ids stay workspace-relative.
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
  if (posix.includes("/workspace/")) {
    return posix.slice(posix.lastIndexOf("/workspace/") + "/workspace/".length);
  }
  if (posix.startsWith("/workspace")) {
    return posix.slice("/workspace".length).replace(/^\/+/, "");
  }

  return posix;
}

/**
 * Workspace API path for dock open / download — always prefer the canonical
 * workspace-relative form when ``agentId`` is known.
 */
export function toDockWorkspaceApiPath(
  raw: string,
  agentId?: string | null,
): string {
  const canonical = canonicalizeDockFilePath(raw, agentId);
  return toWorkspaceApiPath(canonical || raw);
}

/** Display basename for dock tab titles / list rows. */
export function dockFileBasename(path: string): string {
  const normalized = normalizeDockFilePath(path).replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
}

/** Stable tab id for an open file path. */
export function dockFileTabId(path: string, agentId?: string | null): string {
  return `file:${canonicalizeDockFilePath(path, agentId)}`;
}

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

/** Deduplicate by canonical workspace path; keep the richest display path. */
export function dedupeDockFilePaths(
  paths: string[],
  agentId?: string | null,
): string[] {
  const bestByKey = new Map<string, string>();
  const order: string[] = [];
  for (const raw of paths) {
    const key = canonicalizeDockFilePath(raw, agentId);
    if (!key) continue;
    const display = normalizeDockFilePath(raw) || key;
    const prev = bestByKey.get(key);
    if (!prev) {
      bestByKey.set(key, preferDisplayPath(key, display));
      order.push(key);
      continue;
    }
    bestByKey.set(key, preferDisplayPath(prev, display));
  }
  return order.map((key) => bestByKey.get(key) || key);
}

/**
 * Path form for agent workspace download / tree APIs
 * (absolute → ``file://``, legacy ``/outbound`` → relative).
 */
export function toWorkspaceApiPath(resolvedPath: string): string {
  const raw = resolvedPath.trim();
  if (!raw) return raw;
  if (raw.toLowerCase().startsWith("file://")) {
    return raw;
  }
  const posix = raw.replace(/\\/g, "/");
  if (
    posix.startsWith("/outbound/") ||
    posix.startsWith("/inbound/") ||
    posix === "/outbound" ||
    posix === "/inbound"
  ) {
    return posix.replace(/^\//, "");
  }
  if (posix.startsWith("/") || /^[A-Za-z]:/.test(raw)) {
    return posix.startsWith("/") ? `file://${posix}` : `file:///${posix}`;
  }
  return posix;
}

export type DockPathTreeNode = {
  /** Directory segment key (joined for collapsed chains) or file basename. */
  name: string;
  /** Full path for files; directory prefix for folders. */
  path: string;
  isDir: boolean;
  children: DockPathTreeNode[];
};

/**
 * Build a folder tree from flat paths, collapsing single-child directory
 * chains into ``a / b / c`` labels (PR “Files changed” style).
 */
export function buildDockPathTree(
  paths: string[],
  agentId?: string | null,
): DockPathTreeNode[] {
  type Trie = {
    name: string;
    path: string;
    isDir: boolean;
    children: Map<string, Trie>;
  };

  const root: Trie = {
    name: "",
    path: "",
    isDir: true,
    children: new Map(),
  };

  for (const raw of dedupeDockFilePaths(paths, agentId)) {
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
      let child = node.children.get(part);
      if (!child) {
        child = {
          name: part,
          path: acc,
          isDir: !isLast,
          children: new Map(),
        };
        node.children.set(part, child);
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
