import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

/** Clickable unread count. Opens that expert's unread thread. */
export default function AgentUnreadBadge({
  count,
  onOpen,
}: {
  count: number;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  if (!count || count <= 0) return null;
  const text = count > 99 ? "99+" : count;
  return (
    <button
      type="button"
      className={styles.agentUnreadBadge}
      aria-label={t("chat.unreadMessages", "未读消息")}
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      {text}
    </button>
  );
}
