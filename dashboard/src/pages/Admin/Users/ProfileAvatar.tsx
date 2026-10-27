import { request, requestUpload } from "../../../api/request";
import {
  ResourceAvatar,
  ResourceAvatarPicker,
  ROLE_AVATAR_PRESETS,
  resolveAvatarPreset as resolveCatalogPreset,
  USER_AVATAR_PRESETS,
  type AvatarPresetCatalog,
} from "../../../components/AvatarPicker";
import styles from "./index.module.less";

export type AvatarKind = "user" | "role";

function presetsFor(kind: AvatarKind): AvatarPresetCatalog {
  return kind === "role" ? ROLE_AVATAR_PRESETS : USER_AVATAR_PRESETS;
}

export function resolveAvatarPreset(kind: AvatarKind, icon?: string | null) {
  return resolveCatalogPreset(presetsFor(kind), icon);
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
  return (
    <ResourceAvatar
      url={url}
      icon={icon}
      defaultIcon={defaultIcon}
      presets={presetsFor(kind)}
      className={className}
    />
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
  return (
    <ResourceAvatarPicker
      imageUrl={avatarUrl}
      presetId={icon}
      presets={presetsFor(kind)}
      disabled={disabled}
      previewLarge={kind === "role"}
      onPick={onPick}
      onSelectPreset={onSelectIcon}
      onRemove={onRemove}
    />
  );
}
