import {
  CheckCircle2,
  Circle,
  CircleDot,
  Loader2,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  countCompletedTodos,
  type TodoListItem,
} from "../utils/parseWriteTodos";
import styles from "./TodoProgressPanel.module.less";

function statusIcon(status: TodoListItem["status"], isStreaming: boolean) {
  if (status === "in_progress" && isStreaming) {
    return <Loader2 size={16} className={styles.todoStatusInProgressSpin} />;
  }
  switch (status) {
    case "completed":
      return <CheckCircle2 size={16} className={styles.todoStatusCompleted} />;
    case "in_progress":
      return <CircleDot size={16} className={styles.todoStatusInProgress} />;
    case "cancelled":
      return <XCircle size={16} className={styles.todoStatusCancelled} />;
    default:
      return <Circle size={16} className={styles.todoStatusPending} />;
  }
}

export function TodoListView({
  items,
  isStreaming = false,
  className,
  variant = "inline",
}: {
  items: readonly TodoListItem[];
  isStreaming?: boolean;
  className?: string;
  variant?: "inline" | "panel";
}) {
  const { t } = useTranslation();
  if (items.length === 0) return null;

  const completed = countCompletedTodos(items);

  return (
    <div
      className={[
        styles.todoListBlock,
        variant === "panel" ? styles.todoProgressPanel : null,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className={styles.todoListHeader}>
        <div className={styles.todoListTitle}>
          {t("chatUsage.todoListTitle", "Task progress")}
        </div>
        <div className={styles.todoListSummary}>
          {t("chatUsage.todoListSummary", {
            completed,
            total: items.length,
            defaultValue: "{{completed}}/{{total}} done",
          })}
        </div>
      </div>
      <ul className={styles.todoListItems}>
        {items.map((item) => (
          <li key={item.id} className={styles.todoListItem}>
            <span className={styles.todoListIcon}>
              {statusIcon(item.status, isStreaming)}
            </span>
            <span
              className={`${styles.todoListText} ${
                item.status === "completed"
                  ? styles.todoListTextCompleted
                  : item.status === "cancelled"
                  ? styles.todoListTextCancelled
                  : ""
              }`}
            >
              {item.content}
            </span>
            <span className={styles.todoListStatus}>
              {t(`chatUsage.todoStatus.${item.status}`, item.status)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TodoProgressPanel({
  items,
  isStreaming = false,
  followingProcessSummary = false,
}: {
  items: readonly TodoListItem[];
  isStreaming?: boolean;
  followingProcessSummary?: boolean;
}) {
  return (
    <TodoListView
      items={items}
      isStreaming={isStreaming}
      variant="panel"
      className={
        followingProcessSummary ? styles.followingProcessSummary : undefined
      }
    />
  );
}
