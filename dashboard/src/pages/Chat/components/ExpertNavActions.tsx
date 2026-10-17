import { useTranslation } from "react-i18next";
import { MessageSquarePlus, Pin } from "lucide-react";
import styles from "../index.module.less";

function ExpertPinButton({
  pinned,
  className,
  onToggle,
}: {
  pinned: boolean;
  className: string;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const label = pinned ? t("chat.expertUnpin") : t("chat.expertPin");
  return (
    <button
      type="button"
      className={`${className} ${pinned ? styles.agentPinBtnActive : ""}`}
      aria-label={label}
      aria-pressed={pinned}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
    >
      <Pin size={12} strokeWidth={2} aria-hidden />
    </button>
  );
}

/** Pin control to the right of the new-chat button on an expert nav row. */
export default function ExpertNavActions({
  variant,
  pinned,
  onTogglePin,
  onNewChat,
}: {
  variant: "classic" | "minimal";
  pinned: boolean;
  onTogglePin: () => void;
  onNewChat: () => void;
}) {
  const { t } = useTranslation();
  const pinClass =
    variant === "minimal" ? styles.minimalAgentPinBtn : styles.agentPinBtn;
  const newChatClass =
    variant === "minimal"
      ? styles.minimalAgentNewChatBtn
      : styles.agentNewChatBtn;
  return (
    <span
      className={styles.expertNavActions}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        className={newChatClass}
        aria-label={t("chatWelcome.newChat")}
        title={t("chatWelcome.newChat")}
        onClick={(e) => {
          e.stopPropagation();
          onNewChat();
        }}
      >
        <MessageSquarePlus size={14} strokeWidth={1.75} aria-hidden />
      </button>
      <ExpertPinButton
        pinned={pinned}
        className={pinClass}
        onToggle={onTogglePin}
      />
    </span>
  );
}
