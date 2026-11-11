import type { AvatarPreset } from "../types";

/** Bundled expert cartoon stems under ``public/experts/avatars/``. */
const EXPERT_PORTRAIT_IDS = [
  "general-assistant",
  "scene-tech",
  "scene-office",
  "scene-data",
  "scene-design",
  "scene-education",
  "scene-finance",
  "scene-healthcare",
  "scene-hr",
  "scene-legal",
  "scene-marketing",
  "scene-media",
  "scene-content-creation",
  "scene-ecommerce",
  "ai-coding-coach",
  "stock-assistant",
  "parenting-companion",
] as const;

/**
 * Portraits that are the same drawing as another preset. The file stays so
 * existing experts keep their URL; the picker shows the canonical tile.
 */
const PRESET_ALIASES: Record<string, string> = {
  "news-trend": "scene-media",
};

export function canonicalExpertPresetId(id: string | null): string | null {
  if (!id || id === "default") return null;
  return PRESET_ALIASES[id] ?? id;
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
