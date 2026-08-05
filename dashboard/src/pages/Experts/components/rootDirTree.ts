export interface DirTreeNode {
  value: string;
  title: string;
  isLeaf?: boolean;
  children?: DirTreeNode[];
}

export const ROOT_NODE: DirTreeNode = {
  value: "/",
  title: "/",
  isLeaf: false,
};

export function pathExistsInTree(nodes: DirTreeNode[], path: string): boolean {
  for (const node of nodes) {
    if (node.value === path) return true;
    if (node.children?.length && pathExistsInTree(node.children, path)) {
      return true;
    }
  }
  return false;
}

/**
 * Keep the selected value displayable without inventing root-level orphans.
 * Orphans duplicate nested keys and break Ant Design TreeSelect expand/rename.
 */
export function ensurePathInTree(
  nodes: DirTreeNode[],
  path: string,
): DirTreeNode[] {
  if (!path || pathExistsInTree(nodes, path)) {
    return nodes;
  }
  return nodes;
}

/** Keep a single `/` tree — root-level orphans duplicate keys and break expand. */
export function sanitizeTree(nodes: DirTreeNode[]): DirTreeNode[] {
  const root = nodes.find((node) => node.value === "/");
  return root ? [root] : nodes;
}

/**
 * Ancestor directories from `/` down to the parent of *path* (excludes *path*).
 * POSIX absolute paths only (dashboard root_dir picker).
 */
export function ancestorDirPaths(path: string): string[] {
  const normalized = path.trim();
  if (!normalized || normalized === "/") return [];
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0) return [];
  const ancestors: string[] = ["/"];
  let current = "";
  for (const part of parts.slice(0, -1)) {
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

  const walk = (list: DirTreeNode[]): DirTreeNode[] =>
    list.map((node) => {
      if (found) return node;
      if (node.value === parentPath) {
        found = true;
        const existing = node.children ?? [];
        const seen = new Set(existing.map((child) => child.value));
        const merged = [
          ...existing,
          ...children.filter((child) => !seen.has(child.value)),
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

  const walk = (list: DirTreeNode[]): DirTreeNode[] =>
    list.map((node) => {
      if (found) return node;
      if (node.value === oldPath) {
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
