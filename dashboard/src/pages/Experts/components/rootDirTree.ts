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

/** Keep a single tree under *treeRoot* — orphans duplicate keys and break expand. */
export function sanitizeTree(
  nodes: DirTreeNode[],
  treeRoot: string = HOST_FS_ROOT,
): DirTreeNode[] {
  const rootValue = normalizeTreeRoot(treeRoot);
  const rootKey = compareKey(rootValue);
  const root = nodes.find((node) => compareKey(node.value) === rootKey);
  if (!root) return nodes;

  // Ant Design TreeSelect virtual scroll renders duplicate rows when the same
  // value appears more than once anywhere in treeData (antd#37228).
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

  const cleaned = walk(root);
  return cleaned ? [cleaned] : [root];
}

/**
 * Ancestor directories from *treeRoot* down to the parent of *path* (excludes *path*).
 */
export function ancestorDirPaths(
  path: string,
  treeRoot: string = HOST_FS_ROOT,
): string[] {
  const normalized = normalizeTreeRoot(path);
  const root = normalizeTreeRoot(treeRoot);
  if (!normalized || compareKey(normalized) === compareKey(root)) return [];
  if (root !== HOST_FS_ROOT && !isPathUnderHome(normalized, root)) {
    return [];
  }

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
