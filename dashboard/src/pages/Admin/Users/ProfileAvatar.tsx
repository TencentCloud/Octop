import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Button } from "antd";
import {
  Code2,
  Cog,
  Crown,
  Feather,
  ImagePlus,
  Landmark,
  Megaphone,
  PieChart,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { message } from "@/utils/antdMessage";
import { request, requestUpload } from "../../../api/request";
import adminPortrait from "../../../assets/avatars/admin.png";
import bossPortrait from "../../../assets/avatars/boss.png";
import doctorPortrait from "../../../assets/avatars/doctor.png";
import financePortrait from "../../../assets/avatars/finance.png";
import nursePortrait from "../../../assets/avatars/nurse.png";
import opsPortrait from "../../../assets/avatars/ops.png";
import staffPortrait from "../../../assets/avatars/staff.png";
import studentPortrait from "../../../assets/avatars/student.png";
import supportPortrait from "../../../assets/avatars/support.png";
import teacherPortrait from "../../../assets/avatars/teacher.png";
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
  Icon?: LucideIcon;
  src?: string;
}

const USER_PRESETS: AvatarPreset[] = [
  {
    id: "user",
    labelKey: "adminUsers.avatarIconUser",
    bg: "#e8f1ff",
    fg: "#175cd3",
    Icon: UserRound,
  },
  {
    id: "admin",
    labelKey: "adminUsers.avatarIconAdmin",
    bg: "",
    fg: "",
    src: adminPortrait,
  },
  {
    id: "staff",
    labelKey: "adminUsers.avatarIconStaff",
    bg: "",
    fg: "",
    src: staffPortrait,
  },
  {
    id: "doctor",
    labelKey: "adminUsers.avatarIconDoctor",
    bg: "",
    fg: "",
    src: doctorPortrait,
  },
  {
    id: "nurse",
    labelKey: "adminUsers.avatarIconNurse",
    bg: "",
    fg: "",
    src: nursePortrait,
  },
  {
    id: "student",
    labelKey: "adminUsers.avatarIconStudent",
    bg: "",
    fg: "",
    src: studentPortrait,
  },
  {
    id: "teacher",
    labelKey: "adminUsers.avatarIconTeacher",
    bg: "",
    fg: "",
    src: teacherPortrait,
  },
  {
    id: "support",
    labelKey: "adminUsers.avatarIconSupport",
    bg: "",
    fg: "",
    src: supportPortrait,
  },
  {
    id: "ops",
    labelKey: "adminUsers.avatarIconOps",
    bg: "",
    fg: "",
    src: opsPortrait,
  },
  {
    id: "finance",
    labelKey: "adminUsers.avatarIconFinance",
    bg: "",
    fg: "",
    src: financePortrait,
  },
  {
    id: "boss",
    labelKey: "adminUsers.avatarIconBoss",
    bg: "",
    fg: "",
    src: bossPortrait,
  },
];

const ROLE_PRESETS: AvatarPreset[] = [
  {
    id: "member",
    labelKey: "adminUsers.avatarIconMember",
    bg: "",
    fg: "",
    Icon: Users,
  },
  {
    id: "award",
    labelKey: "adminUsers.avatarIconAward",
    bg: "",
    fg: "",
    Icon: Crown,
  },
  {
    id: "terminal",
    labelKey: "adminUsers.avatarIconTerminal",
    bg: "",
    fg: "",
    Icon: Code2,
  },
  {
    id: "pen",
    labelKey: "adminUsers.avatarIconPen",
    bg: "",
    fg: "",
    Icon: Feather,
  },
  {
    id: "chart",
    labelKey: "adminUsers.avatarIconChart",
    bg: "",
    fg: "",
    Icon: PieChart,
  },
  {
    id: "headset",
    labelKey: "adminUsers.avatarIconHeadset",
    bg: "",
    fg: "",
    Icon: Megaphone,
  },
  {
    id: "wrench",
    labelKey: "adminUsers.avatarIconWrench",
    bg: "",
    fg: "",
    Icon: Cog,
  },
  {
    id: "scale",
    labelKey: "adminUsers.avatarIconScale",
    bg: "",
    fg: "",
    Icon: Landmark,
  },
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
    input.addEventListener("change", () => resolve(input.files?.[0] ?? null), {
      once: true,
    });
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
  const portrait = !photo && Boolean(preset.src);
  const tinted = !photo && !portrait && kind !== "role";
  const style: CSSProperties | undefined = tinted
    ? { background: preset.bg, color: preset.fg }
    : undefined;
  const PresetIcon = preset.Icon;
  return (
    <span
      className={[className, portrait ? styles.presetPortrait : ""]
        .filter(Boolean)
        .join(" ")}
      style={style}
    >
      {photo ? (
        <img src={src} alt="" />
      ) : portrait ? (
        <img src={preset.src} alt="" className={styles.presetPortraitImg} />
      ) : PresetIcon ? (
        <PresetIcon />
      ) : null}
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
          className={[
            styles.profileAvatarPickerPreview,
            kind === "role" ? styles.profileAvatarPickerPreviewRole : "",
          ]
            .filter(Boolean)
            .join(" ")}
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
      <div className={styles.avatarPresetLabel}>
        {t("adminUsers.avatarSamples")}
      </div>
      <div className={styles.avatarPresetGrid}>
        {presets.map((preset, index) => {
          const selected =
            !hasPhoto && (index === 0 ? !icon : icon === preset.id);
          const label =
            index === 0 ? t("adminUsers.avatarDefault") : t(preset.labelKey);
          const plain = kind === "role";
          const portrait = Boolean(preset.src);
          const PresetIcon = preset.Icon;
          return (
            <button
              key={preset.id}
              type="button"
              className={[
                styles.avatarPreset,
                plain ? styles.avatarPresetPlain : "",
                portrait ? styles.avatarPresetPortrait : "",
                selected ? styles.avatarPresetActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
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
                void Promise.resolve(
                  onSelectIcon?.(index === 0 ? null : preset.id),
                ).catch(() => undefined);
              }}
            >
              {portrait ? (
                <img src={preset.src} alt="" />
              ) : PresetIcon ? (
                <PresetIcon size={plain ? 22 : 18} />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
