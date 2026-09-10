import type { SlashCommandSpec } from "../api/modules/slash";

/** Mirrors backend ``CATEGORY_ORDER`` in ``slash/catalog.py``. */
export const SLASH_CATEGORY_ORDER = [
  "core",
  "skills",
  "session",
  "media",
  "system",
  "debug",
] as const;

export type SlashCategory = (typeof SLASH_CATEGORY_ORDER)[number];

const CATEGORY_LABELS: Record<SlashCategory, { en: string; zh: string }> = {
  core: { en: "Core", zh: "核心命令" },
  skills: { en: "Skills", zh: "技能" },
  session: { en: "Sessions", zh: "会话管理" },
  media: { en: "Media", zh: "多媒体" },
  system: { en: "System", zh: "系统" },
  debug: { en: "Debug", zh: "调试" },
};

export function slashCategoryLabel(category: string, locale: string): string {
  const key = category as SlashCategory;
  const labels = CATEGORY_LABELS[key];
  if (!labels) return category;
  return locale.startsWith("zh") ? labels.zh : labels.en;
}

export interface SlashMenuGroup<T> {
  category: string;
  label: string;
  items: T[];
}

/** Group menu rows by category in catalog order (empty categories omitted). */
export function groupSlashByCategory<T extends { spec: SlashCommandSpec }>(
  items: T[],
  locale: string,
): SlashMenuGroup<T>[] {
  const buckets = new Map<string, T[]>();
  for (const item of items) {
    const cat = item.spec.category || "system";
    const list = buckets.get(cat);
    if (list) list.push(item);
    else buckets.set(cat, [item]);
  }
  return SLASH_CATEGORY_ORDER.filter((cat) => buckets.has(cat)).map((cat) => ({
    category: cat,
    label: slashCategoryLabel(cat, locale),
    items: buckets.get(cat)!,
  }));
}
