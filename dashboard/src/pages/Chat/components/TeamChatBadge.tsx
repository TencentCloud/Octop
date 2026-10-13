import { useTranslation } from "react-i18next";
import { Users } from "lucide-react";
import { isTeamAgent } from "../../../utils/teamAgent";
import styles from "../index.module.less";

interface TeamChatBadgeProps {
  agent?: { kind?: string } | null;
  show?: boolean;
}

/** Marks a sidebar row / title / welcome line as a team group chat. */
export default function TeamChatBadge({ agent, show }: TeamChatBadgeProps) {
  const { t } = useTranslation();
  if (!(show ?? isTeamAgent(agent))) return null;
  const label = t("chat.teamBadge");
  return (
    <span className={styles.teamChatBadge} aria-label={label}>
      <Users size={10} strokeWidth={2.4} aria-hidden />
      {label}
    </span>
  );
}
