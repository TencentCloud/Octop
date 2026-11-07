import { useTranslation } from "react-i18next";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import {
  Eye,
  EyeOff,
  MessageSquarePlus,
  MoreVertical,
  Pin,
  PinOff,
} from "lucide-react";
import styles from "../index.module.less";

/** Small pin shown on a pinned expert row. The action itself stays in the menu. */
export function ExpertPinMark({ pinned }: { pinned: boolean }) {
  const { t } = useTranslation();
  if (!pinned) return null;
  return (
    <span className={styles.sessionRowPinIndicator} title={t("chat.expertPin")}>
      <Pin size={12} strokeWidth={2} aria-hidden />
    </span>
  );
}

/** New-chat button plus a more menu for pin and hide on an expert nav row. */
export default function ExpertNavActions({
  variant,
  pinned,
  onTogglePin,
  onNewChat,
  onHide,
  onUnhide,
}: {
  variant: "classic" | "minimal";
  pinned: boolean;
  onTogglePin: () => void;
  onNewChat: () => void;
  onHide?: () => void;
  onUnhide?: () => void;
}) {
  const { t } = useTranslation();
  const moreClass =
    variant === "minimal" ? styles.minimalAgentMoreBtn : styles.agentMoreBtn;
  const newChatClass =
    variant === "minimal"
      ? styles.minimalAgentNewChatBtn
      : styles.agentNewChatBtn;
  const items: NonNullable<MenuProps["items"]> = [
    {
      key: "pin",
      icon: pinned ? <PinOff size={14} /> : <Pin size={14} />,
      label: pinned ? t("chat.expertUnpin") : t("chat.expertPin"),
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        onTogglePin();
      },
    },
  ];
  if (onHide) {
    items.push({
      key: "hide",
      icon: <EyeOff size={14} />,
      label: t("chat.expertHide"),
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        onHide();
      },
    });
  }
  if (onUnhide) {
    items.push({
      key: "unhide",
      icon: <Eye size={14} />,
      label: t("chat.expertUnhide"),
      onClick: ({ domEvent }) => {
        domEvent.stopPropagation();
        onUnhide();
      },
    });
  }
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
      <Dropdown menu={{ items }} trigger={["click"]} placement="bottomRight">
        <button
          type="button"
          className={moreClass}
          aria-label={t("common.more")}
          aria-haspopup="menu"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreVertical size={14} strokeWidth={2} aria-hidden />
        </button>
      </Dropdown>
    </span>
  );
}
