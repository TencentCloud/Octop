import { useTranslation } from "react-i18next";
import { Tooltip } from "antd";
import { Users } from "lucide-react";
import { isTeamAgent } from "../../../utils/teamAgent";
import styles from "../index.module.less";

interface TeamChatBadgeProps {
  agent?: { kind?: string } | null;
  show?: boolean;
  /** Icon only, matching the compact cloud flag so the name can ellipsize. */
  compact?: boolean;
}

/** Marks a sidebar row / title / welcome line as a team group chat. */
export default function TeamChatBadge({
  agent,
  show,
  compact = false,
}: TeamChatBadgeProps) {
  const { t } = useTranslation();
  if (!(show ?? isTeamAgent(agent))) return null;
  const label = t("chat.teamBadge");
  const badge = (
    <span
      className={`${styles.teamChatBadge}${
        compact ? ` ${styles.teamChatBadgeCompact}` : ""
      }`}
      aria-label={label}
      onClick={(event) => event.stopPropagation()}
    >
      <Users size={compact ? 11 : 10} strokeWidth={2.4} aria-hidden />
      {compact ? null : label}
    </span>
  );
  if (!compact) return badge;
  return (
    <Tooltip title={label} mouseEnterDelay={0.35}>
      {badge}
    </Tooltip>
  );
}
