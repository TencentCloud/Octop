export interface DirTreeNode {
  value: string;
  title: string;
  isLeaf?: boolean;
  children?: DirTreeNode[];
}

/** Host filesystem root — POSIX admins may browse from here. */
export const HOST_FS_ROOT = "/";

export const ROOT_NODE: DirTreeNode = makeRootNode(HOST_FS_ROOT);

/** Normalize separators and trailing slashes for tree keys / comparisons. */
export function normalizeTreeRoot(path: string): string {
  const trimmed = path.trim().replace(/\\/g, "/");
  if (!trimmed || trimmed === "/") return HOST_FS_ROOT;
  // Keep Windows drive roots like ``C:/`` as a single segment with trailing slash.
  if (/^[A-Za-z]:\/?$/.test(trimmed)) {
    return `${trimmed.replace(/\/+$/, "")}/`;
  }
  return trimmed.replace(/\/+$/, "") || HOST_FS_ROOT;
}

function compareKey(path: string): string {
  const normalized = normalizeTreeRoot(path);
  // Drive-letter paths are case-insensitive on Windows hosts.
  if (/^[A-Za-z]:/.test(normalized)) {
    return normalized.toLowerCase();
  }
  return normalized;
}

export function makeRootNode(path: string): DirTreeNode {
  const value = normalizeTreeRoot(path);
  if (value === HOST_FS_ROOT) {
    return { value: HOST_FS_ROOT, title: "/", isLeaf: false };
  }
  if (/^[A-Za-z]:\/$/.test(value)) {
    return { value, title: value.replace(/\/$/, ""), isLeaf: false };
  }
  const title = value.split("/").filter(Boolean).pop() || value;
  return { value, title, isLeaf: false };
}

/** Deduplicated root list; accepts a bare string for single-root callers. */
export function normalizeTreeRoots(roots: string | string[]): string[] {
  const list = Array.isArray(roots) ? roots : [roots];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of list) {
    const value = normalizeTreeRoot(raw);
    const key = compareKey(value);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
  return out.length > 0 ? out : [HOST_FS_ROOT];
}

export function makeRootNodes(roots: string | string[]): DirTreeNode[] {
  return normalizeTreeRoots(roots).map(makeRootNode);
}

export function isTreeRoot(path: string, roots: string | string[]): boolean {
  const key = compareKey(normalizeTreeRoot(path));
  return normalizeTreeRoots(roots).some((root) => compareKey(root) === key);
}

/** True when *path* is *home* or a subdirectory of *home*. */
export function isPathUnderHome(path: string, home: string): boolean {
  const target = compareKey(path);
  const base = compareKey(home);
  if (base === HOST_FS_ROOT) return true;
  const basePrefix = base.endsWith("/") ? base.slice(0, -1) : base;
  return (
    target === base ||
    target === basePrefix ||
    target.startsWith(`${basePrefix}/`)
  );
}

export function pathExistsInTree(nodes: DirTreeNode[], path: string): boolean {
  const needle = compareKey(path);
  for (const node of nodes) {
    if (compareKey(node.value) === needle) return true;
    if (node.children?.length && pathExistsInTree(node.children, path)) {
      return true;
    }
  }
  return false;
}

/** Keep one tree per root under *treeRoots* — orphans duplicate keys and break expand. */
export function sanitizeTree(
  nodes: DirTreeNode[],
  treeRoots: string | string[] = HOST_FS_ROOT,
): DirTreeNode[] {
  const rootKeys = normalizeTreeRoots(treeRoots).map(compareKey);

  // Ant Design TreeSelect virtual scroll renders duplicate rows when the same
  // value appears more than once anywhere in treeData (antd#37228). The set is
  // shared across roots: every drive root is a distinct path, so global
  // uniqueness is still the correct rule.
  const seen = new Set<string>();

  const walk = (node: DirTreeNode): DirTreeNode | null => {
    const key = compareKey(node.value);
    if (seen.has(key)) return null;
    seen.add(key);
    const children = (node.children ?? [])
      .map(walk)
      .filter((child): child is DirTreeNode => child != null);
    return {
      ...node,
      children: children.length > 0 ? children : undefined,
    };
  };

  const cleaned: DirTreeNode[] = [];
  for (const node of nodes) {
    if (!rootKeys.includes(compareKey(node.value))) continue;
    const walked = walk(node);
    if (walked) cleaned.push(walked);
  }
  // Safety valve: a rename/mkdir that moved every root away should not blank
  // the picker — keep the caller's nodes rather than rendering nothing.
  return cleaned.length > 0 ? cleaned : nodes;
}

/**
 * Ancestor directories from the most specific containing root down to the
 * parent of *path* (excludes *path*). Returns [] when *path* sits outside
 * every configured root, or when it *is* a root.
 */
export function ancestorDirPaths(
  path: string,
  treeRoots: string | string[] = HOST_FS_ROOT,
): string[] {
  const normalized = normalizeTreeRoot(path);
  if (!normalized) return [];
  const roots = normalizeTreeRoots(treeRoots);
  // Longest-prefix wins so Windows `D:/x/y` expands under `D:/` even when
  // `C:/` is listed first.
  const root = roots
    .filter((candidate) => isPathUnderHome(normalized, candidate))
    .reduce<string | null>(
      (best, candidate) =>
        best === null || compareKey(candidate).length > compareKey(best).length
          ? candidate
          : best,
      null,
    );
  if (root === null) return [];
  if (compareKey(normalized) === compareKey(root)) return [];

  if (/^[A-Za-z]:\/$/.test(root)) {
    // Windows drive root: build from ``C:/Users/...`` under ``C:/``.
    const withoutDrive = normalized.replace(/^[A-Za-z]:\/?/, "");
    const parts = withoutDrive.split("/").filter(Boolean);
    if (parts.length === 0) return [];
    const ancestors: string[] = [root];
    let current = root.replace(/\/$/, "");
    for (const part of parts.slice(0, -1)) {
      current += `/${part}`;
      ancestors.push(current);
    }
    return ancestors;
  }

  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0) return [];
  const rootParts =
    root === HOST_FS_ROOT ? [] : root.split("/").filter(Boolean);
  const ancestors: string[] = [root];
  let current = root === HOST_FS_ROOT ? "" : root;
  for (const part of parts.slice(rootParts.length, -1)) {
    current += `/${part}`;
    ancestors.push(current);
  }
  return ancestors;
}

export function appendChildren(
  nodes: DirTreeNode[],
  parentPath: string,
  children: DirTreeNode[],
): DirTreeNode[] {
  let found = false;
  const parentKey = compareKey(parentPath);

  const walk = (list: DirTreeNode[]): DirTreeNode[] =>
    list.map((node) => {
      if (found) return node;
      if (compareKey(node.value) === parentKey) {
        found = true;
        const existing = node.children ?? [];
        const seen = new Set(existing.map((child) => compareKey(child.value)));
        const merged = [
          ...existing,
          ...children.filter((child) => !seen.has(compareKey(child.value))),
        ];
        return { ...node, children: merged };
      }
      if (node.children?.length) {
        return {
          ...node,
          children: walk(node.children),
        };
      }
      return node;
    });

  return walk(nodes);
}

export function insertChild(
  nodes: DirTreeNode[],
  parentPath: string,
  child: DirTreeNode,
): DirTreeNode[] {
  return appendChildren(nodes, parentPath, [child]);
}

export function renameNode(
  nodes: DirTreeNode[],
  oldPath: string,
  newPath: string,
  newName: string,
): DirTreeNode[] {
  let found = false;
  const oldKey = compareKey(oldPath);

  const walk = (list: DirTreeNode[]): DirTreeNode[] =>
    list.map((node) => {
      if (found) return node;
      if (compareKey(node.value) === oldKey) {
        found = true;
        return { ...node, value: newPath, title: newName };
      }
      if (node.children?.length) {
        return {
          ...node,
          children: walk(node.children),
        };
      }
      return node;
    });

  return walk(nodes);
}
