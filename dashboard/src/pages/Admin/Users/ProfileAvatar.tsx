import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Button } from "antd";
import {
  Award,
  BookOpen,
  Briefcase,
  ChartColumn,
  FlaskConical,
  GraduationCap,
  Headset,
  ImagePlus,
  Laptop,
  Palette,
  PenLine,
  Scale,
  SquareUser,
  Stethoscope,
  Terminal,
  UserRound,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { request, requestUpload } from "../../../api/request";
import { useAuthImageSrc } from "../../../hooks/useAuthImageSrc";
import { validateAvatarFile } from "../../Experts/components/ExpertAvatarPicker";
import styles from "./index.module.less";

const AVATAR_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";

export type AvatarKind = "user" | "role";

interface AvatarPreset {
  id: string;
  labelKey: string;
  bg: string;
  fg: string;
  Icon: LucideIcon;
}

const USER_PRESETS: AvatarPreset[] = [
  { id: "user", labelKey: "adminUsers.avatarIconUser", bg: "#e8f1ff", fg: "#175cd3", Icon: UserRound },
  { id: "business", labelKey: "adminUsers.avatarIconBusiness", bg: "#fff4d6", fg: "#b54708", Icon: Briefcase },
  { id: "research", labelKey: "adminUsers.avatarIconResearch", bg: "#f4ebff", fg: "#6941c6", Icon: FlaskConical },
  { id: "medical", labelKey: "adminUsers.avatarIconMedical", bg: "#ffe4e8", fg: "#c01048", Icon: Stethoscope },
  { id: "laptop", labelKey: "adminUsers.avatarIconLaptop", bg: "#e0f2fe", fg: "#026aa2", Icon: Laptop },
  { id: "teach", labelKey: "adminUsers.avatarIconTeach", bg: "#f3e8dd", fg: "#93370d", Icon: BookOpen },
  { id: "design", labelKey: "adminUsers.avatarIconDesign", bg: "#fce7f6", fg: "#c11574", Icon: Palette },
  { id: "learner", labelKey: "adminUsers.avatarIconLearner", bg: "#fef7c3", fg: "#a15c07", Icon: GraduationCap },
];

const ROLE_PRESETS: AvatarPreset[] = [
  { id: "member", labelKey: "adminUsers.avatarIconMember", bg: "", fg: "", Icon: SquareUser },
  { id: "award", labelKey: "adminUsers.avatarIconAward", bg: "", fg: "", Icon: Award },
  { id: "terminal", labelKey: "adminUsers.avatarIconTerminal", bg: "", fg: "", Icon: Terminal },
  { id: "pen", labelKey: "adminUsers.avatarIconPen", bg: "", fg: "", Icon: PenLine },
  { id: "chart", labelKey: "adminUsers.avatarIconChart", bg: "", fg: "", Icon: ChartColumn },
  { id: "headset", labelKey: "adminUsers.avatarIconHeadset", bg: "", fg: "", Icon: Headset },
  { id: "wrench", labelKey: "adminUsers.avatarIconWrench", bg: "", fg: "", Icon: Wrench },
  { id: "scale", labelKey: "adminUsers.avatarIconScale", bg: "", fg: "", Icon: Scale },
];

function presetsFor(kind: AvatarKind): AvatarPreset[] {
  return kind === "role" ? ROLE_PRESETS : USER_PRESETS;
}

export function resolveAvatarPreset(
  kind: AvatarKind,
  icon?: string | null,
): AvatarPreset {
  const presets = presetsFor(kind);
  return (icon && presets.find((item) => item.id === icon)) || presets[0];
}

export function uploadUserAvatar(userId: number, file: File) {
  const body = new FormData();
  body.append("file", file);
  return requestUpload<{ avatar_url: string | null }>(
    `/users/${userId}/avatar`,
    body,
  );
}

export function deleteUserAvatar(userId: number) {
  return request<void>(`/users/${userId}/avatar`, { method: "DELETE" });
}

function pickImageFile(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = AVATAR_ACCEPT;
    input.addEventListener(
      "change",
      () => resolve(input.files?.[0] ?? null),
      { once: true },
    );
    input.click();
  });
}

export function ProfileAvatar({
  url,
  icon,
  defaultIcon,
  kind = "user",
  className,
}: {
  url?: string | null;
  icon?: string | null;
  defaultIcon?: string | null;
  kind?: AvatarKind;
  className?: string;
}) {
  const trimmed = url?.trim() || "";
  const { src, loadState } = useAuthImageSrc(trimmed);
  const photo = Boolean(trimmed) && loadState === "ready" && Boolean(src);
  const preset = resolveAvatarPreset(kind, icon ?? defaultIcon);
  const tinted = !photo && kind !== "role";
  const style: CSSProperties | undefined = tinted
    ? { background: preset.bg, color: preset.fg }
    : undefined;
  return (
    <span className={className} style={style}>
      {photo ? <img src={src} alt="" /> : <preset.Icon />}
    </span>
  );
}

export function RoleSelectLabel({
  url,
  icon,
  label,
}: {
  url?: string | null;
  icon?: string | null;
  label: string;
}) {
  return (
    <span className={styles.roleSelectOption}>
      <ProfileAvatar
        url={url}
        icon={icon}
        kind="role"
        className={styles.roleSelectIcon}
      />
      <span className={styles.roleSelectName}>{label}</span>
    </span>
  );
}

export function ProfileAvatarPicker({
  avatarUrl,
  icon,
  kind = "user",
  disabled = false,
  onPick,
  onSelectIcon,
  onRemove,
}: {
  avatarUrl?: string | null;
  icon?: string | null;
  kind?: AvatarKind;
  disabled?: boolean;
  onPick: (file: File) => void | Promise<void>;
  onSelectIcon?: (icon: string | null) => void | Promise<void>;
  onRemove?: () => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const localPreviewRef = useRef<string | null>(null);
  const displayUrl = localPreview ?? avatarUrl;
  const hasPhoto = Boolean(displayUrl?.trim());
  const presets = presetsFor(kind);

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
    <div className={styles.profileAvatarPicker}>
      <div className={styles.profileAvatarPickerHead}>
        <ProfileAvatar
          url={displayUrl}
          icon={icon}
          kind={kind}
          className={styles.profileAvatarPickerPreview}
        />
        <div className={styles.profileAvatarPickerActions}>
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
                }
              });
            }}
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
          <span className={styles.profileAvatarPickerHint}>
            {t("experts.avatarHint")}
          </span>
        </div>
      </div>
      <div className={styles.avatarPresetLabel}>{t("adminUsers.avatarSamples")}</div>
      <div className={styles.avatarPresetGrid}>
        {presets.map((preset, index) => {
          const selected =
            !hasPhoto && (index === 0 ? !icon : icon === preset.id);
          const label =
            index === 0 ? t("adminUsers.avatarDefault") : t(preset.labelKey);
          const plain = kind === "role";
          return (
            <button
              key={preset.id}
              type="button"
              className={[
                styles.avatarPreset,
                plain ? styles.avatarPresetPlain : "",
                selected ? styles.avatarPresetActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
              style={
                plain ? undefined : { background: preset.bg, color: preset.fg }
              }
              disabled={disabled}
              aria-pressed={selected}
              aria-label={label}
              title={label}
              onClick={() => {
                replaceLocalPreview(null);
                void Promise.resolve(
                  onSelectIcon?.(index === 0 ? null : preset.id),
                ).catch(() => undefined);
              }}
            >
              <preset.Icon size={18} />
            </button>
          );
        })}
      </div>
    </div>
  );
}
