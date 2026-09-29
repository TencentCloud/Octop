import type { ReactNode } from "react";
import { Tag, Tooltip } from "antd";
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

interface TeamSpeakerRowProps extends ExpertMessageAvatarProps {
  /** Display name — rendered next to the avatar (T-34 ①). */
  displayName: string;
  /**
   * The speaker's role, taken **verbatim from the roster data**
   * (``team_run_members.role`` / ``manifest.members[].role``). This component keeps
   * **no role vocabulary of its own**: inventing a list here would move "who is what"
   * back out of the data that T-33 just put it in (AM-4).
   */
  role?: string | null;
  /** ``team_run_members.is_lead`` / ``manifest.lead_agent_id`` — data, not a guess. */
  isLead?: boolean;
}

/**
 * One room message speaker: avatar + name + role tag (T-34 ①).
 *
 * The avatar half is the existing :func:`ExpertMessageAvatar` (click ⇒ profile drawer);
 * this wrapper adds the two facts the room view was missing — the **name** and the
 * **role**, both passed in from the run snapshot.
 */
export function TeamSpeakerRow({
  displayName,
  role,
  isLead,
  ...avatarProps
}: TeamSpeakerRowProps) {
  const { t } = useTranslation();
  const name = displayName.trim();
  return (
    <div className="flex items-center gap-2" data-testid="team-speaker-row">
      <ExpertMessageAvatar {...avatarProps} name={avatarProps.name ?? name} />
      <span data-testid="team-speaker-name" className="text-sm">
        {name}
      </span>
      {role ? (
        <Tag data-testid="team-speaker-role" className="m-0">
          {role}
        </Tag>
      ) : null}
      {isLead ? (
        <Tag color="gold" className="m-0" data-testid="team-speaker-lead">
          {t("teamRuns.roster.leadBadge")}
        </Tag>
      ) : null}
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
