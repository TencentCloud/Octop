import { iconForName } from "../../Experts/components/iconForName";
import { AvatarImage } from "../../../components/AvatarImage";
import styles from "../index.module.less";

export interface ChatAgentOption {
  agent_id: string;
  name: string;
  icon_name?: string | null;
  color?: string | null;
  avatar_url?: string | null;
  is_shared?: boolean;
  is_owner?: boolean;
  owner_username?: string | null;
}

interface ExpertAgentAvatarProps {
  iconName?: string | null;
  color?: string | null;
  /** Uploaded avatar URL; when set it replaces the icon+color circle. */
  avatarUrl?: string | null;
  name?: string;
  /** Lucide icon size inside the circle. */
  iconSize?: number;
  /** Avatar circle diameter in px. */
  size?: number;
  className?: string;
  /** Neutral styling for read-only history tags. */
  muted?: boolean;
}

export default function ExpertAgentAvatar({
  iconName,
  color,
  avatarUrl,
  name,
  iconSize,
  size = 32,
  className,
  muted = false,
}: ExpertAgentAvatarProps) {
  const accent = muted ? "#94a3b8" : color || "#6366f1";
  const inner = iconSize ?? Math.max(12, Math.round(size * 0.55));

  return (
    <span
      className={`${styles.expertAgentAvatar} ${className ?? ""}`}
      style={{
        width: size,
        height: size,
        color: accent,
        background: muted ? "rgba(148, 163, 184, 0.14)" : `${accent}1a`,
      }}
      aria-hidden={name ? undefined : true}
      role={name ? "img" : undefined}
      aria-label={name}
    >
      {iconForName(iconName, inner)}
      <AvatarImage avatarUrl={avatarUrl} size={size} alt={name ?? ""} />
    </span>
  );
}
