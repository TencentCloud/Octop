import { CornerDownLeft, Paperclip, Pencil, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { QueuedChatItem } from "../hooks/useChatMessageQueue";
import styles from "../index.module.less";

interface ChatQueuedMessagesProps {
  items: QueuedChatItem[];
  onRemove: (id: string) => void;
  onReclaim: (id: string) => void;
  /** Commit a local draft as a mid-turn steer. */
  onSteer?: (id: string) => void;
}

function previewText(item: QueuedChatItem): string {
  return item.text.trim().replace(/\s+/g, " ");
}

export default function ChatQueuedMessages({
  items,
  onRemove,
  onReclaim,
  onSteer,
}: ChatQueuedMessagesProps) {
  const { t } = useTranslation();

  if (items.length === 0) return null;

  return (
    <div
      className={styles.queuedMessages}
      role="list"
      aria-label={t("chat.queue.label")}
    >
      {items.map((item, index) => {
        const text = previewText(item);
        const attachmentCount = item.attachments?.length ?? 0;
        const label =
          text ||
          (attachmentCount > 0
            ? t("chat.queue.attachmentsOnly", {
                count: attachmentCount,
              })
            : t("chat.queue.emptyItem"));
        const canSteer = Boolean(onSteer);

        return (
          <div
            key={item.id}
            className={styles.queuedMessageItem}
            role="listitem"
          >
            {items.length > 1 ? (
              <span className={styles.queuedMessageIndex}>{index + 1}</span>
            ) : null}
            <div className={styles.queuedMessageBody}>
              <span className={styles.queuedMessageText}>{label}</span>
              {attachmentCount > 0 && text && (
                <span
                  className={styles.queuedMessageAttach}
                  title={t("chat.queue.attachmentCount", {
                    count: attachmentCount,
                  })}
                >
                  <Paperclip size={12} />
                  {attachmentCount}
                </span>
              )}
            </div>
            <div className={styles.queuedMessageActions}>
              {canSteer ? (
                <button
                  type="button"
                  className={styles.queuedMessageIconBtn}
                  onClick={() => onSteer?.(item.id)}
                  title={t("chat.steer.hint")}
                  aria-label={t("chat.steer.action", "Steer")}
                >
                  <CornerDownLeft size={14} aria-hidden />
                </button>
              ) : null}
              <button
                type="button"
                className={styles.queuedMessageIconBtn}
                onClick={() => onReclaim(item.id)}
                aria-label={t("chat.queue.reclaim")}
                title={t("chat.queue.reclaim")}
              >
                <Pencil size={14} />
              </button>
              <button
                type="button"
                className={styles.queuedMessageIconBtn}
                onClick={() => onRemove(item.id)}
                aria-label={t("chat.queue.remove")}
                title={t("chat.queue.remove")}
              >
                <X size={14} />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
