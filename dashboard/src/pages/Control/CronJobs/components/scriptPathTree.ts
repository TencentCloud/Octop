/** Workspace tree rows shaped for the cron script picker. */

export interface WorkspaceTreeEntry {
  path: string;
  is_dir?: boolean;
}

export interface ScriptPathNode {
  title: string;
  /** Full relative path shown in the closed select. Directories omit it. */
  label?: string;
  value: string;
  selectable: boolean;
  isLeaf: boolean;
  children?: ScriptPathNode[];
}

/** Workspace-relative path stored on the cron job. Leading slashes are dropped. */
export function scriptPathFromTree(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
}

/** Directories to load, shallow to deep, so a saved path can show its label. */
export function scriptPathAncestors(path: string): string[] {
  const parts = scriptPathFromTree(path).split("/").filter(Boolean);
  parts.pop();
  const dirs = [""];
  let acc = "";
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part;
    dirs.push(acc);
  }
  return dirs;
}

const SCRIPT_EXTENSIONS: Record<string, readonly string[]> = {
  python: [".py", ".pyw"],
  bash: [".sh", ".bash"],
  powershell: [".ps1", ".psm1"],
};

function entryName(path: string): string {
  const parts = scriptPathFromTree(path).split("/").filter(Boolean);
  return parts[parts.length - 1] || path;
}

/** True when the file matches the script language chosen in the form. */
export function isScriptFile(path: string, lang: string): boolean {
  const name = entryName(path).toLowerCase();
  const extensions = SCRIPT_EXTENSIONS[lang] ?? SCRIPT_EXTENSIONS.python;
  return extensions.some((ext) => name.endsWith(ext));
}

/** Script files are selectable. Other files stay hidden. Directories only expand. */
export function scriptPathNodes(
  entries: WorkspaceTreeEntry[],
  lang = "python",
): ScriptPathNode[] {
  const nodes: ScriptPathNode[] = [];
  for (const entry of entries) {
    const full = scriptPathFromTree(entry.path || "");
    const name = entryName(full);
    if (!name || name === ".octop") continue;
    if (!entry.is_dir && !isScriptFile(full, lang)) continue;
    if (entry.is_dir) {
      nodes.push({
        title: name,
        value: `dir:${full}`,
        selectable: false,
        isLeaf: false,
      });
      continue;
    }
    nodes.push({
      title: name,
      label: full,
      value: full,
      selectable: true,
      isLeaf: true,
    });
  }
  nodes.sort((a, b) => {
    if (a.isLeaf !== b.isLeaf) return a.isLeaf ? 1 : -1;
    return a.title.localeCompare(b.title);
  });
  return nodes;
}

export function insertScriptPathChildren(
  nodes: ScriptPathNode[],
  dir: string,
  children: ScriptPathNode[],
): ScriptPathNode[] {
  const target = `dir:${dir}`;
  return nodes.map((node) => {
    if (node.value === target) return { ...node, children };
    if (!node.children) return node;
    return {
      ...node,
      children: insertScriptPathChildren(node.children, dir, children),
    };
  });
}
