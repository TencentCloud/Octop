import cx from "classnames";

import { SharedAvatarMark } from "../../../components/SharedResourceBadge";
import { ExpertIcon } from "../../Experts/components/iconForName";
import { ManagedAvatarMark } from "../../Experts/components/ManagedAvatarMark";
import styles from "../index.module.less";

export interface ChatAgentOption {
  agent_id: string;
  name: string;
  icon_name?: string | null;
  icon_url?: string | null;
  color?: string | null;
  is_shared?: boolean;
  is_owner?: boolean;
  owner_username?: string | null;
  /** Remote cloud-collab shadow expert. */
  bridge?: boolean;
  bridge_connection_id?: string | null;
  bridge_connection_name?: string | null;
  bridge_connection_icon?: string | null;
  bridge_disconnected?: boolean;
  bridge_inbound?: boolean;
  /** Bound ACP runner when this expert is managed. */
  managed_runner?: string | null;
}

interface ExpertAgentAvatarProps {
  iconName?: string | null;
  iconUrl?: string | null;
  color?: string | null;
  /** Lucide icon size inside the circle. */
  iconSize?: number;
  /** Avatar circle diameter in px. */
  size?: number;
  className?: string;
  /** Neutral styling for read-only history tags. */
  muted?: boolean;
  /** ACP runner id drawn at the bottom-right, same as the expert card. */
  managedRunner?: string | null;
  /** Incoming share. The pip stacks above the runner mark when both apply. */
  shared?: boolean;
  owned?: boolean;
  ownerName?: string | null;
}

export default function ExpertAgentAvatar({
  iconName,
  iconUrl,
  color,
  iconSize,
  size = 32,
  className,
  muted = false,
  managedRunner,
  shared,
  owned = true,
  ownerName,
}: ExpertAgentAvatarProps) {
  const accent = muted ? "#94a3b8" : color || "#6366f1";
  const photo = Boolean(iconUrl?.trim());
  const inner = photo
    ? size
    : iconSize ?? Math.max(12, Math.round(size * 0.55));

  const avatar = (
    <span
      className={cx(styles.expertAgentAvatar, className)}
      style={{
        width: size,
        height: size,
        color: accent,
        background: muted ? "rgba(148, 163, 184, 0.14)" : `${accent}1a`,
      }}
      aria-hidden
    >
      <ExpertIcon iconUrl={iconUrl} iconName={iconName} size={inner} />
    </span>
  );
  return (
    <SharedAvatarMark shared={shared} owned={owned} ownerName={ownerName}>
      <ManagedAvatarMark runner={managedRunner}>{avatar}</ManagedAvatarMark>
    </SharedAvatarMark>
  );
}
