import {
  EXPERT_AVATAR_PRESETS,
  canonicalExpertPresetId,
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
  /** Select a bundled ``/experts/avatars/{id}.svg`` (null = the default portrait). */
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
  // First grid tile is ``default.svg``. Duplicate drawings share that tile.
  const presetId = canonicalExpertPresetId(rawPresetId);

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
          : expertPresetSrc(selectedPreset || "default");
        return (
          <ExpertAgentAvatar
            iconUrl={previewUrl}
            iconName={iconName}
            color={color}
            size={56}
          />
        );
      }}
    />
  );
}
