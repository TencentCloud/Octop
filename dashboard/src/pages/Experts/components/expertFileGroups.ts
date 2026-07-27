import { request } from "../../../api/request";
import { withFromWorkspace } from "../../../utils/fromWorkspace";

export interface NamedFileContent {
  name: string;
  content: string;
}

export interface SkillFileGroup {
  name: string;
  files: NamedFileContent[];
}

/** Split expert template files into root config md and skills/ tree. */
export function groupExpertFiles(files: NamedFileContent[]): {
  configFiles: NamedFileContent[];
  skillGroups: SkillFileGroup[];
} {
  const configFiles = files.filter((f) => !f.name.startsWith("skills/"));
  const skillFiles = files.filter((f) => f.name.startsWith("skills/"));

  const groups: Record<string, SkillFileGroup> = {};
  for (const file of skillFiles) {
    const skillName = file.name.split("/")[1];
    if (!skillName) continue;
    if (!groups[skillName]) {
      groups[skillName] = { name: skillName, files: [] };
    }
    groups[skillName].files.push(file);
  }

  return { configFiles, skillGroups: Object.values(groups) };
}

/** Workspace glob entry from GET /workspace/glob. */
export interface WorkspaceEntry {
  path: string;
  is_dir?: boolean;
}

/** Config .md files at workspace root (excludes skills/ and _builtin_skills/). */
export function filterConfigMdFiles(entries: WorkspaceEntry[]): string[] {
  return entries
    .filter((f) => {
      if (f.is_dir || !f.path?.endsWith(".md")) return false;
      const p = f.path.startsWith("/") ? f.path : `/${f.path}`;
      return !p.startsWith("/skills/") && !p.startsWith("/_builtin_skills/");
    })
    .map((f) => (f.path.startsWith("/") ? f.path : `/${f.path}`))
    .sort();
}

/** List root-level config markdown files (fast tree listing, glob fallback). */
export async function fetchConfigMdFiles(agentId: string): Promise<string[]> {
  const treeEntries = await request<WorkspaceEntry[]>(
    withFromWorkspace(`/agents/${agentId}/workspace/tree?path=/`),
  );
  const fromTree = filterConfigMdFiles(treeEntries);
  if (fromTree.length > 0) return fromTree;

  const globEntries = await request<WorkspaceEntry[]>(
    withFromWorkspace(
      `/agents/${agentId}/workspace/glob?pattern=${encodeURIComponent(
        "**/*.md",
      )}&path=/`,
    ),
  );
  return filterConfigMdFiles(globEntries);
}
