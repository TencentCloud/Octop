/**
 * Markdown helpers for workspace / SkillHub documents that often carry a
 * leading YAML frontmatter block (``---`` ... ``---``).
 */

export interface SplitMarkdownFrontmatter {
  /** Raw YAML between the delimiters, or null when absent. */
  raw: string | null;
  /** Markdown body with frontmatter removed. */
  body: string;
}

/** Fields we surface separately in the expert-market workflow drawer. */
export interface WorkflowFrontmatterMeta {
  name: string | null;
  displayName: string | null;
  version: string | null;
  packageType: string | null;
  children: string[];
}

/**
 * Split a markdown string into YAML frontmatter and body.
 *
 * When no valid frontmatter exists, ``raw`` is null and ``body`` is the
 * original text (leading whitespace trimmed).
 */
export function splitMarkdownFrontmatter(s: string): SplitMarkdownFrontmatter {
  const match = s.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) {
    return { raw: null, body: s.replace(/^\uFEFF/, "").trimStart() };
  }
  return {
    raw: match[1] ?? "",
    body: s
      .slice(match[0].length)
      .replace(/^\uFEFF/, "")
      .trimStart(),
  };
}

/**
 * Strip YAML frontmatter from the beginning of a markdown string.
 *
 * Many .md files start with a YAML header wrapped in `---` delimiters.
 * Markdown renderers treat `---` as <hr> and dump the YAML as plain text.
 */
export const stripFrontmatter = (s: string): string =>
  splitMarkdownFrontmatter(s).body;

function yamlTopLevelScalar(block: string, key: string): string | null {
  const re = new RegExp(`^${key}:\\s*(.+?)\\s*$`, "m");
  const match = block.match(re);
  if (!match) return null;
  const value = (match[1] || "").trim();
  if (
    !value ||
    value === ">" ||
    value === ">-" ||
    value === "|" ||
    value === "|-"
  ) {
    return null;
  }
  return value.replace(/^["']|["']$/g, "").trim() || null;
}

function yamlIndentedScalar(
  block: string,
  parentKey: string,
  childKey: string,
): string | null {
  const parentRe = new RegExp(`^${parentKey}:\\s*$`, "m");
  const parentMatch = parentRe.exec(block);
  if (!parentMatch || parentMatch.index == null) return null;
  const after = block.slice(parentMatch.index + parentMatch[0].length);
  const childRe = new RegExp(`^[ \\t]+${childKey}:\\s*(.+?)\\s*$`, "m");
  const childMatch = after.match(childRe);
  if (!childMatch) return null;
  // Stop if we left the parent indent scope (another top-level key).
  const between = after.slice(0, childMatch.index ?? 0);
  if (
    /^[A-Za-z_][\w-]*:\s*$/m.test(between) ||
    /^[A-Za-z_][\w-]*:\s+\S/m.test(between)
  ) {
    // another top-level-looking key appeared before the child — still ok if
    // those lines are indented; reject only unindented keys.
    const lines = between.split(/\r?\n/);
    for (const line of lines) {
      if (!line.trim()) continue;
      if (/^[A-Za-z_][\w-]*:/.test(line)) return null;
    }
  }
  const value = (childMatch[1] || "").trim();
  if (
    !value ||
    value === ">" ||
    value === ">-" ||
    value === "|" ||
    value === "|-"
  ) {
    return null;
  }
  return value.replace(/^["']|["']$/g, "").trim() || null;
}

function yamlChildList(block: string): string[] {
  const marker = block.match(/^orchestration:\s*$/m);
  if (!marker || marker.index == null) return [];
  const afterOrch = block.slice(marker.index + marker[0].length);
  const childrenMarker = afterOrch.match(/^[ \t]+children:\s*$/m);
  if (!childrenMarker || childrenMarker.index == null) return [];
  const afterChildren = afterOrch.slice(
    childrenMarker.index + childrenMarker[0].length,
  );
  const items: string[] = [];
  for (const line of afterChildren.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const item = line.match(/^[ \t]+-\s+(.+?)\s*$/);
    if (!item) break;
    const value = (item[1] || "").replace(/^["']|["']$/g, "").trim();
    if (value) items.push(value);
  }
  return items;
}

/** Extract a few UI-friendly fields from SkillHub workflow frontmatter. */
export function parseWorkflowFrontmatterMeta(
  raw: string | null | undefined,
): WorkflowFrontmatterMeta {
  const block = raw ?? "";
  return {
    name: yamlTopLevelScalar(block, "name"),
    displayName: yamlIndentedScalar(block, "metadata", "display_name"),
    version: yamlTopLevelScalar(block, "version"),
    packageType: yamlIndentedScalar(block, "metadata", "package_type"),
    children: yamlChildList(block),
  };
}
