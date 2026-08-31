import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Dropdown } from "antd";
import type { MenuProps } from "antd";
import { useTranslation } from "react-i18next";
import {
  MoreVertical,
  Pin,
  PinOff,
  Pencil,
  Trash2,
  GitFork,
} from "lucide-react";
import { showConfirmModal } from "../../../utils/confirmModal";
import type { Session } from "../hooks/useSessions";
import SessionChannelIcon from "./SessionChannelIcon";
import styles from "../index.module.less";
import { DESKTOP_DRAG_REGION_CLASS } from "../../../utils/desktopChrome";

interface ChatTitleBarProps {
  session: Session;
  title: string;
  onRename: (id: string, name: string) => void;
  onPin: (id: string, pinned: boolean) => void;
  onFork: (id: string) => void;
  onDelete: (id: string) => void;
  forkDisabled?: boolean;
  forkDisabledHint?: string;
}

export default function ChatTitleBar({
  session,
  title,
  onRename,
  onPin,
  onFork,
  onDelete,
  forkDisabled,
  forkDisabledHint,
}: ChatTitleBarProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isEditing) setEditValue(title);
  }, [title, isEditing]);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [isEditing]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== session.name) {
      onRename(session.id, trimmed);
    } else {
      setEditValue(title);
    }
    setIsEditing(false);
  }, [editValue, session.id, session.name, onRename, title]);

  const menuItems: MenuProps["items"] = useMemo(
    () => [
      {
        key: "pin",
        label: session.pinned
          ? t("chat.unpin", "取消置顶")
          : t("chat.pin", "置顶"),
        icon: session.pinned ? <PinOff size={14} /> : <Pin size={14} />,
        onClick: () => onPin(session.id, !session.pinned),
      },
      {
        key: "fork",
        label: t("chat.fork", "分叉"),
        icon: <GitFork size={14} />,
        disabled: forkDisabled,
        title: forkDisabled && forkDisabledHint ? forkDisabledHint : undefined,
        onClick: () => onFork(session.id),
      },
      {
        key: "delete",
        label: t("common.delete"),
        icon: <Trash2 size={14} />,
        danger: true,
        onClick: () => {
          showConfirmModal({
            title: t("chat.deleteSessionConfirm"),
            okText: t("common.delete"),
            cancelText: t("common.cancel"),
            okButtonProps: { danger: true },
            onOk: () => {
              onDelete(session.id);
            },
          });
        },
      },
    ],
    [
      session.id,
      session.pinned,
      onPin,
      onFork,
      onDelete,
      forkDisabled,
      forkDisabledHint,
      t,
    ],
  );

  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <div className={`${styles.chatTitleBar} ${DESKTOP_DRAG_REGION_CLASS}`}>
      <div className={styles.chatTitleLeft}>
        <SessionChannelIcon
          channelType={session.channelType}
          size={13}
          className={styles.chatTitleLeadingIcon}
        />
        {isEditing ? (
          <input
            ref={inputRef}
            className={styles.chatTitleInput}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitEdit();
              if (e.key === "Escape") {
                setEditValue(title);
                setIsEditing(false);
              }
            }}
          />
        ) : (
          <div className={styles.chatTitleHeading}>
            <h1 className={styles.chatTitleText} title={title}>
              {title}
            </h1>
            {session.pinned ? (
              <Pin
                size={13}
                strokeWidth={2}
                className={styles.chatTitlePinMark}
                aria-hidden
              />
            ) : null}
            <button
              type="button"
              className={styles.chatTitleEditBtn}
              onClick={() => setIsEditing(true)}
              aria-label={t("common.edit")}
              title={t("common.edit")}
            >
              <Pencil size={14} strokeWidth={2} aria-hidden />
            </button>
            <Dropdown
              menu={{ items: menuItems }}
              trigger={["click"]}
              placement="bottomLeft"
              onOpenChange={setMoreOpen}
            >
              <button
                type="button"
                className={`${styles.chatTitleEditBtn} ${
                  moreOpen ? styles.chatTitleHoverShown : ""
                }`}
                aria-label={t("common.more", "更多")}
              >
                <MoreVertical size={14} strokeWidth={2} aria-hidden />
              </button>
            </Dropdown>
          </div>
        )}
      </div>
    </div>
  );
}
