import type { ReactNode } from "react";
import { Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import ExpertAgentAvatar from "./ExpertAgentAvatar";
import { useChatAgentProfile } from "../ChatAgentProfileContext";
import styles from "../index.module.less";

/** Shared message-row avatar size. */
export const MESSAGE_AVATAR_SIZE = 36;

interface MessageSenderProps {
  name: string;
  avatar: ReactNode;
}

/** Plain message-row avatar. Name is an accessible label only. */
export default function MessageSender({ name, avatar }: MessageSenderProps) {
  const label = name.trim();
  return (
    <div className={styles.msgSender} aria-label={label || undefined}>
      <span className={styles.msgAvatarPlain} aria-hidden>
        {avatar}
      </span>
    </div>
  );
}

interface ExpertMessageAvatarProps {
  name?: string | null;
  color?: string | null;
  iconName?: string | null;
  iconUrl?: string | null;
  /** Hover label; defaults to ``name``. */
  tooltip?: string | null;
  /** Open this agent in the profile drawer (member vs team host). */
  profileAgentId?: string | null;
}

export function ExpertMessageAvatar({
  name,
  color,
  iconName,
  iconUrl,
  tooltip,
  profileAgentId,
}: ExpertMessageAvatarProps) {
  const { t } = useTranslation();
  const profile = useChatAgentProfile();
  const label = (tooltip ?? name)?.trim() || "";
  const canOpen = Boolean(profile?.canOpen);
  const avatar = (
    <ExpertAgentAvatar
      iconName={iconName}
      iconUrl={iconUrl}
      color={color}
      size={MESSAGE_AVATAR_SIZE}
    />
  );

  const node = canOpen ? (
    <button
      type="button"
      className={styles.msgSenderBtn}
      onClick={() => profile?.openAgentProfile(profileAgentId ?? undefined)}
      aria-label={
        label ||
        t(
          profile?.isTeam
            ? "chat.agentProfile.openTeam"
            : "chat.agentProfile.open",
        )
      }
    >
      {avatar}
    </button>
  ) : (
    <div className={styles.msgSender} aria-label={label || undefined}>
      <span className={styles.msgAvatarPlain} aria-hidden>
        {avatar}
      </span>
    </div>
  );

  if (!label) return node;
  return (
    <Tooltip title={label} mouseEnterDelay={0.35}>
      {node}
    </Tooltip>
  );
}
