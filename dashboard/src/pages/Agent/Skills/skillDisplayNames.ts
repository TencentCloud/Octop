/**
 * Resolve skill presentation names for the dashboard.
 *
 * Preference (UI locale aware):
 * 1. ``metadata.octop.label`` map from the API
 * 2. ``display_name``
 * 3. Localized API ``name`` when it differs from the slug
 * 4. Dashboard / API i18n ``skills.<slug>`` (and hyphen/underscore variants)
 * 5. slug
 */

import { useTranslation } from "react-i18next";
import { normalizeUiLocale, type UiLocale } from "../../../utils/locale";
import { pickLocale, type LocalizedText } from "../../../utils/localizedText";

export interface SkillLabelInput {
  slug?: string;
  name?: string;
  /** Localized map from ``metadata.octop.label``. */
  label?: string | LocalizedText | Record<string, string | undefined>;
  display_name?: string;
  displayName?: string;
}

function asLocalizedText(
  value: SkillLabelInput["label"],
): LocalizedText | undefined {
  if (!value) return undefined;
  if (typeof value === "string") {
    const text = value.trim();
    return text ? { zh: text, en: text } : undefined;
  }
  const zh = typeof value.zh === "string" ? value.zh.trim() : "";
  const en = typeof value.en === "string" ? value.en.trim() : "";
  if (!zh && !en) return undefined;
  return { zh: zh || undefined, en: en || undefined };
}

function slugI18nKeys(slug: string): string[] {
  const keys = [`skills.${slug}`];
  if (slug.includes("-")) keys.push(`skills.${slug.replace(/-/g, "_")}`);
  if (slug.includes("_")) keys.push(`skills.${slug.replace(/_/g, "-")}`);
  return keys;
}

export function resolveSkillDisplayName(
  skill: SkillLabelInput,
  locale: string = "zh",
): string {
  const loc: UiLocale = normalizeUiLocale(locale);
  const slug = (skill.slug ?? "").trim();

  const fromLabel = pickLocale(asLocalizedText(skill.label), loc);
  if (fromLabel) return fromLabel;

  const displayName = (skill.displayName ?? skill.display_name ?? "").trim();
  if (displayName) return displayName;

  const name = (skill.name ?? "").trim();
  // Prefer a human title over the bare directory slug.
  if (name && slug && name.toLowerCase() !== slug.toLowerCase()) return name;
  return name || slug;
}

export function useSkillDisplayName(): (skill: SkillLabelInput) => string {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;

  return (skill: SkillLabelInput) => {
    const resolved = resolveSkillDisplayName(skill, locale);
    const slug = (skill.slug ?? "").trim();
    // If we already have a friendly title (label / display_name / localized name),
    // keep it. Only consult i18n when the result is still the bare slug.
    if (resolved && slug && resolved.toLowerCase() !== slug.toLowerCase()) {
      return resolved;
    }

    for (const key of slugI18nKeys(slug)) {
      const translated = t(key, { defaultValue: "" });
      if (translated && translated !== key) return translated;
    }

    return resolved || slug;
  };
}

/** Resolve by slug alone (e.g. expert template preview before agent exists). */
export function useSkillSlugDisplayName(): (slug: string) => string {
  const skillDisplayName = useSkillDisplayName();
  return (slug: string) => skillDisplayName({ slug });
}
