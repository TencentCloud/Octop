import { request } from "../../../api/request";
import { withFromWorkspace } from "../../../utils/fromWorkspace";
import { parseSkillPreviewFromMarkdown } from "../../Agent/Skills/skillMarkdown";
import { parseSubagentForm } from "./SubagentDrawer";

export interface NamedFileContent {
  name: string;
  content: string;
}

export interface SkillFileGroup {
  name: string;
  files: NamedFileContent[];
  emoji: string;
  displayName: string;
  description: string;
}

export interface SubagentFilePreview {
  slug: string;
  name: string;
  description: string;
  emoji: string;
  file: NamedFileContent;
}

function isSubagentPath(name: string): boolean {
  return name.startsWith("agents/") && name.endsWith(".md");
}

function isPromptMdPath(name: string): boolean {
  return !name.includes("/") && name.endsWith(".md");
}

/** Split expert template files into persona md, skills/, and subagent definitions. */
export function groupExpertFiles(files: NamedFileContent[]): {
  configFiles: NamedFileContent[];
  skillGroups: SkillFileGroup[];
  subagentFiles: SubagentFilePreview[];
} {
  const configFiles = files.filter(
    (f) =>
      isPromptMdPath(f.name) &&
      f.name !== "manifest.json" &&
      !f.name.startsWith("skills/") &&
      !isSubagentPath(f.name),
  );
  const skillFiles = files.filter((f) => f.name.startsWith("skills/"));
  const subagentRaw = files.filter((f) => isSubagentPath(f.name));

  const groups: Record<string, SkillFileGroup> = {};
  for (const file of skillFiles) {
    const skillName = file.name.split("/")[1];
    if (!skillName) continue;
    if (!groups[skillName]) {
      groups[skillName] = {
        name: skillName,
        files: [],
        emoji: "✨",
        displayName: skillName,
        description: "",
      };
    }
    groups[skillName].files.push(file);
  }

  for (const group of Object.values(groups)) {
    const skillMd = group.files.find((f) => f.name.endsWith("/SKILL.md"))
      ?.content;
    if (!skillMd) continue;
    const preview = parseSkillPreviewFromMarkdown(skillMd, group.name);
    group.emoji = preview.emoji;
    group.displayName = preview.name;
    group.description = preview.description;
  }

  const subagentFiles = subagentRaw
    .map((file) => {
      const slug = file.name.slice("agents/".length, -".md".length);
      const parsed = parseSubagentForm(file.content, slug);
      return {
        slug,
        name: parsed.name || slug,
        description: parsed.description,
        emoji: parsed.emoji || "🤖",
        file,
      };
    })
    .sort((a, b) => a.slug.localeCompare(b.slug));

  return { configFiles, skillGroups: Object.values(groups), subagentFiles };
}

/** Workspace glob entry from GET /workspace/glob. */
export interface WorkspaceEntry {
  path: string;
  is_dir?: boolean;
}

/**
 * Persona markdown listed under config files. Order matches the labeled
 * badges in ``iconForName``. ``SKILL.md`` stays with skills.
 */
const CONFIG_MD_ORDER = [
  "SOUL.md",
  "IDENTITY.md",
  "USER.md",
  "AGENTS.md",
  "TOOLS.md",
  "BOOTSTRAP.md",
  "HEARTBEAT.md",
  "MEMORY.md",
  "PROACTIVE.md",
] as const;

const CONFIG_MD_NAMES = new Set<string>(CONFIG_MD_ORDER);

function rootConfigMdName(path: string): string | null {
  let rel = path.replace(/\\/g, "/").trim();
  while (rel.startsWith("/")) rel = rel.slice(1);
  if (rel.startsWith("./")) rel = rel.slice(2);
  if (!rel || rel.includes("/")) return null;
  return CONFIG_MD_NAMES.has(rel) ? rel : null;
}

/** Known root config markdown only (SOUL.md, AGENTS.md, …). */
export function filterConfigMdFiles(entries: WorkspaceEntry[]): string[] {
  const found = new Set<string>();
  for (const entry of entries) {
    if (entry.is_dir || !entry.path) continue;
    const name = rootConfigMdName(entry.path);
    if (name) found.add(name);
  }
  return CONFIG_MD_ORDER.filter((name) => found.has(name)).map(
    (name) => `/${name}`,
  );
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
