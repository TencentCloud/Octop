import {
  EXPERT_AVATAR_PRESETS,
  expertPresetSrc,
  ResourceAvatarPicker,
  splitExpertAvatarUrl,
  validateAvatarFile,
} from "../../../components/AvatarPicker";
import ExpertAgentAvatar from "../../Chat/components/ExpertAgentAvatar";

export { validateAvatarFile };

interface ExpertAvatarPickerProps {
  iconUrl?: string | null;
  iconName?: string | null;
  color?: string | null;
  disabled?: boolean;
  onPick: (file: File) => void | Promise<void>;
  /** Select a bundled ``/experts/avatars/{id}.svg`` (null = clear to Lucide). */
  onSelectPreset?: (presetId: string | null) => void | Promise<void>;
  onRemove?: () => void | Promise<void>;
}

export default function ExpertAvatarPicker({
  iconUrl,
  iconName,
  color,
  disabled = false,
  onPick,
  onSelectPreset,
  onRemove,
}: ExpertAvatarPickerProps) {
  const { imageUrl, presetId: rawPresetId } = splitExpertAvatarUrl(iconUrl);
  // First grid tile is the Lucide fallback; treat bundled ``default.svg`` the same.
  const presetId = rawPresetId === "default" ? null : rawPresetId;

  return (
    <ResourceAvatarPicker
      imageUrl={imageUrl}
      presetId={presetId}
      presets={EXPERT_AVATAR_PRESETS}
      disabled={disabled}
      onPick={onPick}
      onSelectPreset={onSelectPreset}
      onRemove={onRemove}
      renderPreview={({ displayUrl, presetId: selectedPreset, hasPhoto }) => {
        const previewUrl = hasPhoto
          ? displayUrl
          : selectedPreset && selectedPreset !== "default"
          ? expertPresetSrc(selectedPreset)
          : null;
        return (
          <ExpertAgentAvatar
            iconUrl={previewUrl}
            iconName={iconName}
            color={color}
            size={56}
          />
        );
      }}
      renderPreset={({ preset, index }) => {
        // Default tile must match the large preview (Lucide ``icon_name``).
        if (index === 0) {
          return (
            <ExpertAgentAvatar iconName={iconName} color={color} size={36} />
          );
        }
        if (preset.src) {
          return <img src={preset.src} alt="" />;
        }
        const PresetIcon = preset.Icon;
        return PresetIcon ? <PresetIcon size={22} /> : null;
      }}
    />
  );
}
