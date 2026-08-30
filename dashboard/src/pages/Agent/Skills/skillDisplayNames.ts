/**
 * Resolve API-provided presentation names. ``name`` is the localized label
 * from the list API; ``slug`` is the stable identity.
 */

export interface SkillLabelInput {
  slug?: string;
  name?: string;
}

export function resolveSkillDisplayName(skill: SkillLabelInput): string {
  const slug = (skill.slug ?? "").trim();
  const name = (skill.name ?? "").trim();
  if (name && slug && name !== slug) return name;
  return name || slug;
}

export function useSkillDisplayName(): (skill: SkillLabelInput) => string {
  return resolveSkillDisplayName;
}

/** Resolve by slug alone (e.g. expert template preview before agent exists). */
export function useSkillSlugDisplayName(): (slug: string) => string {
  const skillDisplayName = useSkillDisplayName();
  return (slug: string) => skillDisplayName({ slug });
}
