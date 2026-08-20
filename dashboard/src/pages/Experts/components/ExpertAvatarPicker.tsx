import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Modal } from "antd";
import { ImagePlus } from "lucide-react";
import { message } from "@/utils/antdMessage";

import ExpertAgentAvatar from "../../Chat/components/ExpertAgentAvatar";
import styles from "../index.module.less";

export const AVATAR_MAX_BYTES = 5 * 1024 * 1024;
const AVATAR_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";

export function validateAvatarFile(
  file: File,
  t: (key: string) => string,
): string | null {
  if (file.size > AVATAR_MAX_BYTES) {
    return t("experts.avatarTooLarge");
  }
  const type = (file.type || "").split(";")[0].trim().toLowerCase();
  if (
    type &&
    type !== "application/octet-stream" &&
    !AVATAR_ACCEPT.split(",").includes(type)
  ) {
    return t("experts.avatarBadType");
  }
  return null;
}

function pickImageFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = AVATAR_ACCEPT;
    input.addEventListener(
      "change",
      () => {
        resolve(input.files?.[0] ?? null);
      },
      { once: true },
    );
    input.click();
  });
}

interface ExpertAvatarPickerProps {
  iconUrl?: string | null;
  iconName?: string | null;
  color?: string | null;
  disabled?: boolean;
  onPick: (file: File) => void | Promise<void>;
  onRemove?: () => void | Promise<void>;
}

export default function ExpertAvatarPicker({
  iconUrl,
  iconName,
  color,
  disabled = false,
  onPick,
  onRemove,
}: ExpertAvatarPickerProps) {
  const { t } = useTranslation();
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const localPreviewRef = useRef<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const displayUrl = localPreview ?? iconUrl;
  const hasPhoto = Boolean(displayUrl?.trim());

  useEffect(() => {
    return () => {
      if (localPreviewRef.current) {
        URL.revokeObjectURL(localPreviewRef.current);
      }
    };
  }, []);

  const replaceLocalPreview = (next: string | null) => {
    if (localPreviewRef.current) {
      URL.revokeObjectURL(localPreviewRef.current);
    }
    localPreviewRef.current = next;
    setLocalPreview(next);
  };

  const handlePick = () => {
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
      }
    });
  };

  return (
    <div className={styles.avatarPicker}>
      <button
        type="button"
        className={styles.avatarPickerPreviewBtn}
        aria-label={t("experts.avatarPreview")}
        onClick={() => setPreviewOpen(true)}
      >
        <ExpertAgentAvatar
          iconUrl={displayUrl}
          iconName={iconName}
          color={color}
          size={56}
        />
      </button>
      <Modal
        open={previewOpen}
        footer={null}
        centered
        width={320}
        title={t("experts.avatarPreview")}
        onCancel={() => setPreviewOpen(false)}
      >
        <div className={styles.avatarPickerPreviewBody}>
          <ExpertAgentAvatar
            iconUrl={displayUrl}
            iconName={iconName}
            color={color}
            size={220}
          />
        </div>
      </Modal>
      <div className={styles.avatarPickerActions}>
        <Button
          size="small"
          icon={<ImagePlus size={14} />}
          disabled={disabled}
          onClick={handlePick}
        >
          {hasPhoto ? t("experts.avatarChange") : t("experts.avatarUpload")}
        </Button>
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
        <span className={styles.avatarPickerHint}>
          {t("experts.avatarHint")}
        </span>
      </div>
    </div>
  );
}
