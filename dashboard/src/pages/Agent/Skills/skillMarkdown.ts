import { splitMarkdownFrontmatter } from "../../../utils/markdown";
import type { SkillDetail } from "./useSkills";

export const DEFAULT_SKILL_EMOJI = "✨";

function yamlTopLevel(block: string, key: string): string {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const match = block.match(re);
  if (!match) return "";
  return (match[1] || "").trim().replace(/^["']|["']$/g, "");
}

/** Parse display fields from raw SKILL.md for list previews (e.g. expert template). */
export function parseSkillPreviewFromMarkdown(
  content: string,
  slug: string,
): { emoji: string; name: string; description: string } {
  const { raw } = splitMarkdownFrontmatter(content);
  const fm = raw ?? "";
  const name = yamlTopLevel(fm, "name") || slug;
  const description = yamlTopLevel(fm, "description") || "";
  let emoji = DEFAULT_SKILL_EMOJI;
  const emojiMatch = fm.match(/octop:\s*\n\s*emoji:\s*(.+)/);
  if (emojiMatch?.[1]) {
    const value = emojiMatch[1].trim().replace(/^["']|["']$/g, "");
    if (value) emoji = value;
  }
  return { emoji, name, description };
}

export function skillDirectoryPath(
  detail: Pick<SkillDetail, "kind" | "slug">,
): string {
  return detail.kind === "builtin"
    ? `/_builtin_skills/${detail.slug}`
    : `/skills/${detail.slug}`;
}

export function isSkillManifestPath(path: string): boolean {
  const normalized = path.replace(/\\/g, "/");
  return (
    normalized.endsWith("/SKILL.md") ||
    normalized === "SKILL.md" ||
    normalized.endsWith("/skill.md") ||
    normalized === "skill.md"
  );
}

export function skillManifestPath(
  detail: Pick<SkillDetail, "kind" | "slug">,
): string {
  return `${skillDirectoryPath(detail)}/SKILL.md`;
}
