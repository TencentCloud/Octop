/** Insert or replace a leading ``/slug`` skill invoke in composer text. */

const LEADING_SLASH = /^(\s*)(\/[a-zA-Z][\w-]*)(?=\s|$)/;

export function insertSkillSlash(text: string, slug: string): string {
  const token = `/${slug}`;
  const match = text.match(LEADING_SLASH);
  if (match) {
    const rest = text.slice(match[0].length);
    const spaced =
      rest.length === 0
        ? " "
        : rest.startsWith(" ") || rest.startsWith("\n")
        ? rest
        : ` ${rest}`;
    return `${match[1]}${token}${spaced}`;
  }
  const pad = text.length > 0 && !/\s$/.test(text) ? " " : "";
  return `${text}${pad}${token} `;
}

/** Slugs of skills the draft already invokes (its leading ``/slug`` token). */
export function mentionedSkillSlugs(
  text: string,
  skills: ReadonlyArray<{ slug: string }>,
): string[] {
  const match = text.match(LEADING_SLASH);
  if (!match) return [];
  const slug = match[2].slice(1);
  return skills.some((skill) => skill.slug === slug) ? [slug] : [];
}
