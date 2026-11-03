import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

export default function AgentUnreadBadge({
  count,
  onClick,
}: {
  count: number;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  if (count <= 0) return null;
  return (
    <button
      type="button"
      className={styles.agentUnreadBadge}
      aria-label={t("chat.unreadMessages", "未读消息")}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
    >
      {count > 99 ? "99+" : count}
    </button>
  );
}
