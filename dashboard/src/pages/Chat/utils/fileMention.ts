import { request } from "../../../api/request";
import { withFromWorkspace } from "../../../utils/fromWorkspace";

export const WORKSPACE_MENTION_LIMIT = 20;

const SKIP_SEGMENTS = new Set([
  ".octop",
  ".octop-auth",
  "_builtin_skills",
  "node_modules",
  ".git",
  ".venv",
  "__pycache__",
  "inbound",
  "outbound",
]);

export type WorkspaceMentionEntry = {
  path: string;
  is_dir?: boolean;
};

export type WorkspaceMentionFile = {
  path: string;
  label: string;
};

export type WorkspaceMentionHint =
  | "searching"
  | "need_agent"
  | "failed"
  | "typeToSearch"
  | "typeMore"
  | "filesEmpty";

const WORKSPACE_MENTION_MIN_CHARS = 2;

/** Workspace-relative POSIX path: no leading slash, no `..`. */
export function normalizeWorkspaceRelPath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\/+/, "").replace(/\/+$/, "");
}

export function workspaceFileShortName(path: string): string {
  const rel = normalizeWorkspaceRelPath(path);
  return rel.split("/").pop() || rel;
}

export function isSkippedWorkspacePath(path: string): boolean {
  const rel = normalizeWorkspaceRelPath(path);
  if (!rel || rel.split("/").includes("..")) return true;
  return rel.split("/").some((seg) => SKIP_SEGMENTS.has(seg));
}

/** True when the composer should hit glob — never empty `@`, never a single character. */
export function shouldSearchWorkspaceMentions(query: string): boolean {
  return query.trim().length >= WORKSPACE_MENTION_MIN_CHARS;
}

/** Path-shaped queries (`docs/a`, `api.md`) should surface files first. */
export function isPathLikeMentionQuery(query: string): boolean {
  const q = query.trim();
  return q.includes("/") || q.includes(".");
}

/** Replace the open ``@query`` with ``@workspace/rel/path`` (Claude Code style). */
export function replaceFileMentionQuery(
  text: string,
  atIndex: number,
  query: string,
  path: string,
): { text: string; cursor: number } {
  const rel = normalizeWorkspaceRelPath(path);
  const token = rel ? `@${rel}` : "";
  const before = text.slice(0, atIndex);
  const after = text.slice(atIndex + 1 + query.length);
  if (!token) {
    const next = `${before}${after}`.replace(/^\s+/, "");
    return { text: next, cursor: before.length };
  }
  const next = `${before}${token} ${after.replace(/^\s*/, "")}`;
  return { text: next, cursor: before.length + token.length + 1 };
}

export function workspaceMentionHintState(input: {
  query: string;
  loading: boolean;
  error: "need_agent" | "failed" | null;
  fileCount: number;
}): WorkspaceMentionHint | null {
  if (input.loading) return "searching";
  if (input.error) return input.error;
  const q = input.query.trim();
  if (!q) return "typeToSearch";
  if (!shouldSearchWorkspaceMentions(q)) return "typeMore";
  if (input.fileCount === 0) return "filesEmpty";
  return null;
}

export function workspaceGlobPattern(query: string): string {
  const trimmed = query.trim().replace(/\\/g, "/");
  const escaped = trimmed.replace(/[*?[\]{}]/g, "\\$&");
  if (escaped.includes("/")) return `**/${escaped}*`;
  return `**/*${escaped}*`;
}

export function rankWorkspaceMentionFiles(
  entries: WorkspaceMentionEntry[],
  query: string,
): WorkspaceMentionFile[] {
  const q = query.trim().toLowerCase();
  const hits: WorkspaceMentionFile[] = [];
  const seen = new Set<string>();
  for (const entry of entries) {
    if (entry.is_dir) continue;
    const path = normalizeWorkspaceRelPath(String(entry.path || ""));
    if (!path || isSkippedWorkspacePath(path) || seen.has(path)) continue;
    const label = workspaceFileShortName(path);
    if (!label) continue;
    const pathLower = path.toLowerCase();
    const labelLower = label.toLowerCase();
    if (q && !pathLower.includes(q) && !labelLower.includes(q)) continue;
    seen.add(path);
    hits.push({ path, label });
  }
  hits.sort((a, b) => {
    const score = (item: WorkspaceMentionFile) => {
      const name = item.label.toLowerCase();
      const stem = name.includes(".")
        ? name.slice(0, name.lastIndexOf("."))
        : name;
      if (name === q || stem === q) return 0;
      if (name.startsWith(q) || stem.startsWith(q)) return 1;
      if (name.includes(q)) return 2;
      if (item.path.toLowerCase().includes(q)) return 3;
      return 4;
    };
    const diff = score(a) - score(b);
    if (diff !== 0) return diff;
    const depth = a.path.split("/").length - b.path.split("/").length;
    if (depth !== 0) return depth;
    return a.path.localeCompare(b.path);
  });
  return hits.slice(0, WORKSPACE_MENTION_LIMIT);
}

export async function searchWorkspaceMentionFiles(
  agentId: string,
  query: string,
  signal?: AbortSignal,
): Promise<WorkspaceMentionFile[]> {
  if (!shouldSearchWorkspaceMentions(query)) return [];
  const pattern = workspaceGlobPattern(query);
  const entries = await request<WorkspaceMentionEntry[]>(
    withFromWorkspace(
      `/agents/${encodeURIComponent(
        agentId,
      )}/workspace/glob?pattern=${encodeURIComponent(pattern)}&path=/`,
    ),
    signal ? { signal } : {},
  );
  return rankWorkspaceMentionFiles(entries ?? [], query);
}
