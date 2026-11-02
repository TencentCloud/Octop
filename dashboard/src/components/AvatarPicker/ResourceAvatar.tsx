import type { CSSProperties } from "react";

import { useAuthImageSrc } from "../../hooks/useAuthImageSrc";
import styles from "./AvatarPicker.module.less";
import type { AvatarPreset, AvatarPresetCatalog } from "./types";

export function resolveAvatarPreset(
  presets: AvatarPresetCatalog,
  icon?: string | null,
): AvatarPreset {
  if (presets.length === 0) {
    return { id: "default" };
  }
  return (icon && presets.find((item) => item.id === icon)) || presets[0];
}

export function ResourceAvatar({
  url,
  icon,
  defaultIcon,
  presets,
  className,
  large = false,
}: {
  url?: string | null;
  icon?: string | null;
  defaultIcon?: string | null;
  presets: AvatarPresetCatalog;
  className?: string;
  large?: boolean;
}) {
  const trimmed = url?.trim() || "";
  const { src, loadState } = useAuthImageSrc(trimmed);
  const photo = Boolean(trimmed) && loadState === "ready" && Boolean(src);
  const preset = resolveAvatarPreset(presets, icon ?? defaultIcon);
  const portrait = !photo && Boolean(preset.src);
  const plain = preset.tone === "plain" || (!preset.src && !preset.bg);
  const tinted = !photo && !portrait && !plain && Boolean(preset.bg);
  const style: CSSProperties | undefined = tinted
    ? { background: preset.bg, color: preset.fg }
    : undefined;
  const PresetIcon = preset.Icon;
  return (
    <span
      className={[
        styles.preview,
        large ? styles.previewLarge : "",
        portrait ? styles.previewPortrait : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={style}
    >
      {photo ? (
        <img src={src} alt="" />
      ) : portrait ? (
        <img src={preset.src} alt="" className={styles.previewPortraitImg} />
      ) : PresetIcon ? (
        <PresetIcon />
      ) : null}
    </span>
  );
}
