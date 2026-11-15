import type { AvatarPreset } from "../types";

/** Bundled expert cartoon stems under ``public/experts/avatars/``. */
const EXPERT_PORTRAIT_IDS = [
  "general-assistant",
  "scene-tech",
  "scene-office",
  "scene-data",
  "scene-education",
  "scene-healthcare",
  "scene-marketing",
  "parenting-companion",
] as const;

/**
 * Portraits that repeat another preset's drawing (same face and corner
 * prop, palette aside). The file stays so existing experts keep their URL;
 * the picker shows the canonical tile.
 */
const PRESET_ALIASES: Record<string, string> = {
  "news-trend": "scene-marketing",
  "scene-media": "scene-marketing",
  "scene-content-creation": "scene-marketing",
  "scene-ecommerce": "scene-data",
  "stock-assistant": "scene-finance",
  "scene-finance": "scene-office",
  "scene-hr": "scene-education",
  "scene-legal": "scene-education",
  "scene-design": "general-assistant",
  "ai-coding-coach": "scene-tech",
};

export function canonicalExpertPresetId(id: string | null): string | null {
  if (!id || id === "default") return null;
  let current = id;
  const seen = new Set<string>();
  while (PRESET_ALIASES[current] && !seen.has(current)) {
    seen.add(current);
    current = PRESET_ALIASES[current];
  }
  return current;
}

export function expertPresetSrc(id: string): string {
  return `/experts/avatars/${id}.svg`;
}

/** Prefabricated expert portraits; first tile is the bundled default portrait. */
export const EXPERT_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "default",
    labelKey: "adminUsers.avatarDefault",
    src: expertPresetSrc("default"),
  },
  ...EXPERT_PORTRAIT_IDS.map(
    (id): AvatarPreset => ({
      id,
      label: id,
      src: expertPresetSrc(id),
    }),
  ),
];
