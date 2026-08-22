import {
  CheckCircle2,
  ChevronDown,
  Circle,
  CircleDot,
  ListChecks,
  Loader2,
  XCircle,
} from "lucide-react";
import { useState } from "react";
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
  showHeader = true,
}: {
  items: readonly TodoListItem[];
  isStreaming?: boolean;
  className?: string;
  variant?: "inline" | "panel";
  showHeader?: boolean;
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
      {showHeader ? (
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
      ) : null}
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
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const completed = countCompletedTodos(items);
  const current =
    items.find((item) => item.status === "in_progress") ||
    items.find((item) => item.status === "pending");
  const percent = items.length
    ? Math.round((completed / items.length) * 100)
    : 0;
  return (
    <div
      className={`${styles.todoProgressPanel} ${
        followingProcessSummary ? styles.followingProcessSummary : ""
      }`}
    >
      <button
        type="button"
        className={styles.todoPanelHeader}
        onClick={() => setCollapsed((value) => !value)}
        aria-expanded={!collapsed}
      >
        <span className={styles.todoPanelIcon}>
          <ListChecks size={15} />
        </span>
        <span className={styles.todoPanelHeading}>
          <strong>{t("chatUsage.todoListTitle", "Task progress")}</strong>
          <span>
            {current?.content ||
              t("chatUsage.todoListSummary", {
                completed,
                total: items.length,
                defaultValue: "{{completed}}/{{total}} done",
              })}
          </span>
        </span>
        <span className={styles.todoPanelProgressMeta}>
          {completed}/{items.length}
        </span>
        <ChevronDown
          size={14}
          className={`${styles.todoPanelChevron} ${
            collapsed ? styles.todoPanelChevronCollapsed : ""
          }`}
        />
      </button>
      <div className={styles.todoPanelProgressTrack}>
        <span style={{ width: `${percent}%` }} />
      </div>
      {!collapsed ? (
        <TodoListView
          items={items}
          isStreaming={isStreaming}
          showHeader={false}
          className={styles.todoPanelList}
        />
      ) : null}
    </div>
  );
}
