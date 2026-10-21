export type { AvatarPreset, AvatarPresetCatalog } from "./types";
export { ResourceAvatar, resolveAvatarPreset } from "./ResourceAvatar";
export { ResourceAvatarPicker } from "./ResourceAvatarPicker";
export {
  AVATAR_ACCEPT,
  AVATAR_MAX_BYTES,
  pickImageFile,
  validateAvatarFile,
} from "./validate";
export {
  isUploadedAvatarUrl,
  presetIdFromExpertAvatarUrl,
  splitExpertAvatarUrl,
} from "./url";
export { USER_AVATAR_PRESETS } from "./presets/user";
export { ROLE_AVATAR_PRESETS } from "./presets/role";
export { EXPERT_AVATAR_PRESETS, expertPresetSrc } from "./presets/expert";
export { TEAM_AVATAR_PRESETS } from "./presets/team";
export { SKILL_PACKAGE_AVATAR_PRESETS } from "./presets/skillPackage";
export { KNOWLEDGE_AVATAR_PRESETS } from "./presets/knowledge";
export {
  BRIDGE_AVATAR_PRESETS,
  DEFAULT_BRIDGE_AVATAR_ICON,
} from "./presets/bridge";
