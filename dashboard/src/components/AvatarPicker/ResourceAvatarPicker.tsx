import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "antd";
import { ImagePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import cx from "classnames";
import { message } from "@/utils/antdMessage";

import styles from "./AvatarPicker.module.less";
import { ResourceAvatar } from "./ResourceAvatar";
import type { AvatarPreset, AvatarPresetCatalog } from "./types";
import { pickImageFile, validateAvatarFile } from "./validate";

export function ResourceAvatarPicker({
  imageUrl,
  presetId,
  presets,
  disabled = false,
  allowUpload = true,
  previewLarge = false,
  compact = false,
  renderPreview,
  renderPreset,
  onPick,
  onSelectPreset,
  onRemove,
}: {
  /** Uploaded / remote photo URL (wins over preset). */
  imageUrl?: string | null;
  /** Selected prefabricated icon id (``avatar_icon`` / ``icon_name`` / stem). */
  presetId?: string | null;
  presets: AvatarPresetCatalog;
  disabled?: boolean;
  allowUpload?: boolean;
  previewLarge?: boolean;
  compact?: boolean;
  /** Optional custom preview (e.g. expert avatar with accent colour). */
  renderPreview?: (args: {
    displayUrl: string | null;
    presetId: string | null;
    hasPhoto: boolean;
  }) => ReactNode;
  /** Optional custom tile content for the sample-icon grid. */
  renderPreset?: (args: {
    preset: AvatarPreset;
    index: number;
    selected: boolean;
  }) => ReactNode;
  onPick?: (file: File) => void | Promise<void>;
  onSelectPreset?: (presetId: string | null) => void | Promise<void>;
  onRemove?: () => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const presetGridId = useId();
  const presetButton = useRef<HTMLButtonElement>(null);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const presetAvailable = presets.length > 0 && onSelectPreset;
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const localPreviewRef = useRef<string | null>(null);
  const displayUrl = localPreview ?? imageUrl ?? null;
  const hasPhoto = Boolean(displayUrl?.trim());

  useEffect(() => {
    return () => {
      if (localPreviewRef.current) URL.revokeObjectURL(localPreviewRef.current);
    };
  }, []);

  const replaceLocalPreview = (next: string | null) => {
    if (localPreviewRef.current) URL.revokeObjectURL(localPreviewRef.current);
    localPreviewRef.current = next;
    setLocalPreview(next);
  };

  return (
    <div className={styles.picker}>
      <div className={styles.pickerHead}>
        {renderPreview ? (
          renderPreview({
            displayUrl,
            presetId: presetId ?? null,
            hasPhoto,
          })
        ) : (
          <ResourceAvatar
            url={displayUrl}
            icon={presetId}
            presets={presets}
            large={previewLarge}
          />
        )}
        {(allowUpload && onPick) || (compact && presetAvailable) ? (
          <div className={styles.actions}>
            {compact && presetAvailable && (
              <Button
                size="small"
                aria-expanded={presetsOpen}
                aria-controls={presetGridId}
                ref={presetButton}
                disabled={disabled}
                onClick={() => setPresetsOpen((open) => !open)}
              >
                {t("experts.avatarChoosePreset")}
              </Button>
            )}
            {allowUpload && onPick && (
              <Button
                size="small"
                icon={<ImagePlus size={14} />}
                disabled={disabled}
                onClick={() => {
                  void pickImageFile().then(async (file) => {
                    if (!file) return;
                    const err = validateAvatarFile(file, t);
                    if (err) {
                      message.error(err);
                      return;
                    }
                    replaceLocalPreview(URL.createObjectURL(file));
                    try {
                      await onPick(file);
                    } catch {
                      replaceLocalPreview(null);
                      if (compact) {
                        setPresetsOpen(false);
                        presetButton.current?.focus();
                      }
                    }
                  });
                }}
              >
                {hasPhoto
                  ? t("experts.avatarChange")
                  : t("experts.avatarUpload")}
              </Button>
            )}
            {hasPhoto && onRemove ? (
              <Button
                size="small"
                disabled={disabled}
                onClick={() => {
                  replaceLocalPreview(null);
                  void Promise.resolve(onRemove()).catch(() => undefined);
                }}
              >
                {t("experts.avatarRemove")}
              </Button>
            ) : null}
            {!compact && (
              <span className={styles.hint}>{t("experts.avatarHint")}</span>
            )}
          </div>
        ) : null}
      </div>
      {presets.length > 0 && onSelectPreset ? (
        <>
          {!compact && (
            <div className={styles.presetLabel}>
              {t("adminUsers.avatarSamples")}
            </div>
          )}
          <div
            id={presetGridId}
            className={styles.presetGrid}
            style={compact && !presetsOpen ? { display: "none" } : undefined}
          >
            {presets.map((preset, index) => {
              const selected =
                !hasPhoto &&
                (index === 0
                  ? !presetId || presetId === preset.id
                  : presetId === preset.id);
              const label =
                index === 0
                  ? t("adminUsers.avatarDefault")
                  : preset.labelKey
                  ? t(preset.labelKey)
                  : preset.label ?? preset.id;
              const portrait = Boolean(preset.src);
              const plain =
                preset.tone === "plain" || (!portrait && !preset.bg);
              const PresetIcon = preset.Icon;
              return (
                <button
                  key={preset.id}
                  type="button"
                  className={cx(
                    styles.preset,
                    plain && styles.presetPlain,
                    portrait && styles.presetPortrait,
                    selected && styles.presetActive,
                  )}
                  style={
                    plain || portrait
                      ? undefined
                      : { background: preset.bg, color: preset.fg }
                  }
                  disabled={disabled}
                  aria-pressed={selected}
                  aria-label={label}
                  title={label}
                  onClick={() => {
                    replaceLocalPreview(null);
                    if (compact) {
                      setPresetsOpen(false);
                      presetButton.current?.focus();
                    }
                    void Promise.resolve(
                      onSelectPreset(index === 0 ? null : preset.id),
                    ).catch(() => undefined);
                  }}
                >
                  {renderPreset ? (
                    renderPreset({ preset, index, selected })
                  ) : portrait ? (
                    <img src={preset.src} alt="" />
                  ) : PresetIcon ? (
                    <PresetIcon size={plain ? 22 : 18} />
                  ) : null}
                </button>
              );
            })}
          </div>
        </>
      ) : null}
    </div>
  );
}
