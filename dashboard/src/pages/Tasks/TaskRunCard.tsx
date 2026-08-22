import { useEffect, useMemo, useState } from "react";
import { Button, Drawer, Progress, Tag } from "antd";
import {
  ArrowUpRight,
  Check,
  Circle,
  CircleDot,
  Clock3,
  ListChecks,
  Square,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  ThreadTaskItem,
  ThreadTaskSummary,
} from "../../api/modules/octopThreads";
import { formatServerDateTime } from "../../utils/formatMessageTime";
import styles from "./index.module.less";

function itemIcon(item: ThreadTaskItem, running: boolean) {
  if (item.status === "completed") return <Check size={13} />;
  if (item.status === "cancelled") return <X size={13} />;
  if (item.status === "in_progress" || running) return <CircleDot size={13} />;
  return <Circle size={13} />;
}

function currentItem(task: ThreadTaskSummary): ThreadTaskItem | undefined {
  return (
    task.items.find((item) => item.status === "in_progress") ||
    task.items.find((item) => item.status === "pending")
  );
}

function elapsedText(startedAt: number | null, now: number): string {
  if (!startedAt) return "";
  const seconds = Math.max(0, Math.floor(now / 1000) - startedAt);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${rest}s`;
  return `${rest}s`;
}

function LiveElapsed({ startedAt }: { startedAt: number | null }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return <>{elapsedText(startedAt, now)}</>;
}

export function TaskTimeline({
  task,
  limit,
}: {
  task: ThreadTaskSummary;
  limit?: number;
}) {
  const { t } = useTranslation();
  const visibleItems = limit ? task.items.slice(0, limit) : task.items;
  const active = currentItem(task);
  return (
    <ol className={styles.timeline}>
      {visibleItems.map((item) => {
        const isCurrent = item.id === active?.id;
        return (
          <li
            key={item.id}
            className={`${styles.timelineItem} ${
              isCurrent ? styles.timelineItemCurrent : ""
            } ${item.status === "completed" ? styles.timelineItemDone : ""}`}
          >
            <span className={styles.timelineMarker}>
              {itemIcon(item, isCurrent && task.turn_active)}
            </span>
            <span className={styles.timelineContent}>{item.content}</span>
            <span className={styles.timelineStatus}>
              {isCurrent && task.turn_active
                ? t("taskCenter.runningStatus")
                : t(`chatUsage.todoStatus.${item.status}`, item.status)}
            </span>
          </li>
        );
      })}
      {limit && task.items.length > limit ? (
        <li className={styles.timelineMore}>
          {t("taskCenter.moreSteps", { count: task.items.length - limit })}
        </li>
      ) : null}
    </ol>
  );
}

export function TaskRunCard({
  task,
  featured = false,
  onDetails,
  onOpenThread,
  onCancel,
}: {
  task: ThreadTaskSummary;
  featured?: boolean;
  onDetails: () => void;
  onOpenThread: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const active = currentItem(task);
  const percent = task.total
    ? Math.round((task.completed / task.total) * 100)
    : 0;
  const isRunning = task.turn_active;
  const title = task.title || t("taskCenter.untitled");

  return (
    <article
      className={`${styles.runCard} ${featured ? styles.runCardFeatured : ""}`}
    >
      <div
        className={styles.runCardMain}
        role="button"
        tabIndex={0}
        onClick={onDetails}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onDetails();
          }
        }}
      >
        <div className={styles.runCardHeader}>
          <div className={styles.runIdentity}>
            <span
              className={`${styles.liveDot} ${
                isRunning ? styles.liveDotRunning : styles.liveDotWaiting
              }`}
            />
            <div>
              <div className={styles.runEyebrow}>
                {isRunning
                  ? t("taskCenter.currentRun")
                  : task.status === "completed"
                  ? t("taskCenter.completedRun")
                  : t("taskCenter.awaitingRun")}
              </div>
              <h3 className={styles.runTitle}>{title}</h3>
            </div>
          </div>
          <Tag
            color={
              isRunning
                ? "processing"
                : task.status === "completed"
                ? "success"
                : "default"
            }
          >
            {isRunning
              ? t("taskCenter.runningStatus")
              : task.status === "completed"
              ? t("taskCenter.completedStatus")
              : t("taskCenter.waitingStatus")}
          </Tag>
        </div>

        <div className={styles.runMeta}>
          <span>
            <ListChecks size={14} />
            {t("taskCenter.stepProgress", {
              completed: task.completed,
              total: task.total,
            })}
          </span>
          {isRunning && task.turn_started_at ? (
            <span>
              <Clock3 size={14} />
              <LiveElapsed startedAt={task.turn_started_at} />
            </span>
          ) : (
            <span>
              <Clock3 size={14} />
              {formatServerDateTime(task.last_active || task.created_at)}
            </span>
          )}
        </div>

        <Progress
          percent={percent}
          showInfo={false}
          strokeColor={isRunning ? "#1677ff" : "#52c41a"}
          trailColor="var(--fn-border-secondary, rgba(0, 0, 0, 0.08))"
          size="small"
          className={styles.runProgress}
        />

        {active && task.status === "active" ? (
          <div className={styles.currentStep}>
            <span>{t("taskCenter.currentStep")}</span>
            <strong>{active.content}</strong>
          </div>
        ) : null}
        <TaskTimeline task={task} limit={featured ? 5 : 3} />
      </div>

      <div className={styles.runActions}>
        <Button type="text" onClick={onDetails}>
          {t("taskCenter.viewDetails")}
        </Button>
        {isRunning ? (
          <Button danger icon={<Square size={13} />} onClick={onCancel}>
            {t("taskCenter.stopRun")}
          </Button>
        ) : null}
        <Button
          type="primary"
          icon={<ArrowUpRight size={14} />}
          onClick={onOpenThread}
        >
          {task.status === "completed"
            ? t("taskCenter.openThread")
            : t("taskCenter.continueThread")}
        </Button>
      </div>
    </article>
  );
}

export function TaskDetailDrawer({
  task,
  open,
  onClose,
  onOpenThread,
  onCancel,
}: {
  task: ThreadTaskSummary | null;
  open: boolean;
  onClose: () => void;
  onOpenThread: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const percent = useMemo(
    () => (task?.total ? Math.round((task.completed / task.total) * 100) : 0),
    [task],
  );
  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={560}
      title={task?.title || t("taskCenter.untitled")}
      extra={
        task ? (
          <Tag
            color={
              task.turn_active
                ? "processing"
                : task.status === "completed"
                ? "success"
                : "default"
            }
          >
            {task.turn_active
              ? t("taskCenter.runningStatus")
              : task.status === "completed"
              ? t("taskCenter.completedStatus")
              : t("taskCenter.waitingStatus")}
          </Tag>
        ) : null
      }
      footer={
        task ? (
          <div className={styles.drawerFooter}>
            {task.turn_active ? (
              <Button danger icon={<Square size={13} />} onClick={onCancel}>
                {t("taskCenter.stopRun")}
              </Button>
            ) : (
              <span />
            )}
            <Button
              type="primary"
              icon={<ArrowUpRight size={14} />}
              onClick={onOpenThread}
            >
              {task.status === "completed"
                ? t("taskCenter.openThread")
                : t("taskCenter.continueThread")}
            </Button>
          </div>
        ) : null
      }
    >
      {task ? (
        <div className={styles.drawerBody}>
          <div className={styles.drawerSummary}>
            <div>
              <span>{t("taskCenter.progress")}</span>
              <strong>{percent}%</strong>
            </div>
            <Progress percent={percent} showInfo={false} />
            <p>
              {t("taskCenter.stepProgress", {
                completed: task.completed,
                total: task.total,
              })}
              {task.turn_active && task.turn_started_at ? (
                <>
                  {" · "}
                  {t("taskCenter.elapsed")}{" "}
                  <LiveElapsed startedAt={task.turn_started_at} />
                </>
              ) : null}
            </p>
          </div>
          <div className={styles.drawerSectionTitle}>
            {t("taskCenter.executionPlan")}
          </div>
          <TaskTimeline task={task} />
          <div className={styles.drawerThreadMeta}>
            <span>{t("taskCenter.threadId")}</span>
            <code>{task.thread_id}</code>
          </div>
        </div>
      ) : null}
    </Drawer>
  );
}
