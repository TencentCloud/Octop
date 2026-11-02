/**
 * Knowledge-base folder UI helpers.
 * Path math lives in ``utils/knowledgePath``; this module re-exports it and
 * keeps DOM-aware folder-open gating for the KB page.
 */

import {
  knowledgePathParent,
  normalizeKnowledgePath,
} from "../../utils/knowledgePath";

export {
  isDirectKnowledgeChild,
  joinKnowledgePath,
  knowledgeBasename,
  knowledgeBreadcrumb,
  knowledgePathParent,
  normalizeKnowledgePath,
} from "../../utils/knowledgePath";

export function shouldOpenKnowledgeFolder(
  isDir: boolean,
  event?: { target?: EventTarget | null },
): boolean {
  if (!isDir) return false;
  const target = event?.target;
  if (target instanceof Element && target.closest("[data-kb-doc-actions]")) {
    return false;
  }
  return true;
}

/** Sentinel key for the synthetic root row in the document tree. */
export const KNOWLEDGE_DOC_TREE_ROOT = "__kb_root__";

export type KnowledgeFileTreeNode = {
  key: string;
  path: string;
  name: string;
  isDir: boolean;
  children?: KnowledgeFileTreeNode[];
};

type KnowledgeTreeSource = {
  path?: string | null;
  filename: string;
  is_dir?: boolean;
};

export function knowledgeDocumentPath(document: KnowledgeTreeSource): string {
  try {
    return normalizeKnowledgePath(document.path || document.filename);
  } catch {
    return "";
  }
}

type MutableTreeNode = {
  path: string;
  name: string;
  isDir: boolean;
  children: Map<string, MutableTreeNode>;
};

function ensureKnowledgeFolder(
  root: Map<string, MutableTreeNode>,
  folderPath: string,
): Map<string, MutableTreeNode> {
  if (!folderPath) return root;
  let map = root;
  let acc = "";
  for (const part of folderPath.split("/")) {
    acc = acc ? `${acc}/${part}` : part;
    let node = map.get(part);
    if (!node) {
      node = { path: acc, name: part, isDir: true, children: new Map() };
      map.set(part, node);
    } else {
      node.isDir = true;
    }
    map = node.children;
  }
  return map;
}

function freezeKnowledgeTree(
  map: Map<string, MutableTreeNode>,
): KnowledgeFileTreeNode[] {
  return [...map.values()]
    .sort((a, b) => {
      const dirDelta = Number(b.isDir) - Number(a.isDir);
      if (dirDelta !== 0) return dirDelta;
      return a.name.localeCompare(b.name);
    })
    .map((node) => ({
      key: node.path,
      path: node.path,
      name: node.name,
      isDir: node.isDir,
      children: node.isDir ? freezeKnowledgeTree(node.children) : undefined,
    }));
}

/** Folder tree only. Parent folders implied by a file path are included. */
export function buildKnowledgeFileTree(
  documents: KnowledgeTreeSource[],
): KnowledgeFileTreeNode[] {
  const root = new Map<string, MutableTreeNode>();
  for (const document of documents) {
    const path = knowledgeDocumentPath(document);
    if (!path) continue;
    ensureKnowledgeFolder(
      root,
      document.is_dir ? path : knowledgePathParent(path),
    );
  }
  return freezeKnowledgeTree(root);
}
