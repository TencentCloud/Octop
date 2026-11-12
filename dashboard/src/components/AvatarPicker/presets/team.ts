import type { AvatarPreset } from "../types";
import { expertPresetSrc } from "./expert";

/**
 * Team cartoon portraits in the same style as ``team-host``
 * (rounded square, soft gradient, multi-person compositions).
 */
const TEAM_PORTRAIT_IDS = [
  "team-host",
  "team-lead",
  "team-standup",
  "team-pair",
  "team-circle",
  "team-brainstorm",
  "team-remote",
  "team-crew",
] as const;

/** Prefabricated team portraits; first tile is the default team-host cartoon. */
export const TEAM_AVATAR_PRESETS: AvatarPreset[] = TEAM_PORTRAIT_IDS.map(
  (id, index): AvatarPreset => ({
    id,
    labelKey: index === 0 ? "adminUsers.avatarDefault" : undefined,
    label: index === 0 ? undefined : id,
    src: expertPresetSrc(id),
  }),
);
