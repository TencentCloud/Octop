import { useEffect, useMemo, useState } from "react";
import type { DragEvent } from "react";
import {
  Button,
  Checkbox,
  Empty,
  Input,
  Modal,
  Select,
  Spin,
  Tag,
  Timeline,
  Tooltip,
  Typography,
} from "antd";
import {
  CalendarDays,
  Check,
  History,
  Plus,
  Search,
  User,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  projectsApi,
  type ProjectTask,
  type ProjectTaskStatus,
  type ProjectTimelineEvent,
} from "../../../api/modules/projects";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import styles from "./Board.module.less";

const { Text } = Typography;

/** Custom drag type: identifies a board card during a native HTML5 drag. */
const TASK_DRAG_TYPE = "application/x-octop-project-task";

/** Column order; the terminal columns come last and can be hidden. */
const COLUMN_STATUSES: ProjectTaskStatus[] = [
  "todo",
  "doing",
  "review",
  "blocked",
  "done",
  "cancelled",
];

const TERMINAL_STATUSES: ProjectTaskStatus[] = ["done", "cancelled"];

const STATUS_LABEL_KEYS: Record<ProjectTaskStatus, string> = {
  todo: "projects.taskStatusTodo",
  doing: "projects.taskStatusDoing",
  review: "projects.taskStatusReview",
  done: "projects.taskStatusDone",
  blocked: "projects.taskStatusBlocked",
  cancelled: "projects.taskStatusCancelled",
};

const STATUS_COLORS: Record<ProjectTaskStatus, string> = {
  todo: "default",
  doing: "processing",
  review: "warning",
  done: "success",
  blocked: "error",
  cancelled: "default",
};

/**
 * Mirrors `_TASK_TRANSITIONS` in `infra/projects/service.py`. The backend stays
 * authoritative and answers an illegal move with `PROJECT_TASK_STATUS_INVALID`
 * (HTTP 409); illegal drops are refused here so nothing is sent at all.
 */
const STATUS_TRANSITIONS: Record<ProjectTaskStatus, ProjectTaskStatus[]> = {
  todo: ["doing", "blocked", "cancelled"],
  doing: ["todo", "review", "done", "blocked", "cancelled"],
  review: ["doing", "done", "blocked", "cancelled"],
  blocked: ["todo", "doing", "cancelled"],
  done: ["doing"],
  cancelled: [],
};

/** Timeline actions recorded by the backend (`infra/db/repos/project_tasks.py`). */
const TIMELINE_ACTION_KEYS: Record<string, string> = {
  "task.created": "projects.boardActionCreated",
  "task.updated": "projects.boardActionUpdated",
  "task.status_changed": "projects.boardActionStatusChanged",
  "task.assigned": "projects.boardActionAssigned",
  "task.deleted": "projects.boardActionDeleted",
  "task.dispatched": "projects.boardActionDispatched",
};

function isTransitionAllowed(
  from: ProjectTaskStatus,
  to: ProjectTaskStatus,
): boolean {
  return STATUS_TRANSITIONS[from].includes(to);
}

/** Creation is `todo`-only server-side, so only reachable columns offer "add". */
function canCreateInto(status: ProjectTaskStatus): boolean {
  return status === "todo" || isTransitionAllowed("todo", status);
}

function asTaskStatus(value: unknown): ProjectTaskStatus | null {
  return typeof value === "string" &&
    (COLUMN_STATUSES as string[]).includes(value)
    ? (value as ProjectTaskStatus)
    : null;
}

interface BoardProps {
  projectId: string;
  tasks: ProjectTask[];
  /** Archived projects and viewers get a read-only board (no drag, no writes). */
  canEdit: boolean;
  /** Re-read the project tasks after a write so the board mirrors the server. */
  onChanged: () => void | Promise<void>;
}

function Board({ projectId, tasks, canEdit, onChanged }: BoardProps) {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();

  const [titleFilter, setTitleFilter] = useState("");
  // Terminal columns start visible: hiding them is an explicit choice, so a
  // card dragged into Done / Cancelled never disappears on its own.
  const [showTerminal, setShowTerminal] = useState(true);
  const [dragTaskId, setDragTaskId] = useState<string | null>(null);
  const [overStatus, setOverStatus] = useState<ProjectTaskStatus | null>(null);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [addingStatus, setAddingStatus] = useState<ProjectTaskStatus | null>(
    null,
  );
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [timelineTask, setTimelineTask] = useState<ProjectTask | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<ProjectTimelineEvent[]>(
    [],
  );
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<unknown>(null);

  const timelineTaskId = timelineTask?.task_id ?? null;

  useEffect(() => {
    if (!timelineTaskId) return;
    let cancelled = false;
    setTimelineLoading(true);
    setTimelineError(null);
    // No `limit`: the API pages from the oldest event, so a bounded read could
    // hide a task's recent history.
    projectsApi
      .timeline(projectId)
      .then((events) => {
        if (cancelled) return;
        setTimelineEvents(
          events.filter((event) => event.task_id === timelineTaskId),
        );
      })
      .catch((error: unknown) => {
        if (!cancelled) setTimelineError(error);
      })
      .finally(() => {
        if (!cancelled) setTimelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, timelineTaskId]);

  const filteredTasks = useMemo(() => {
    const query = titleFilter.trim().toLowerCase();
    if (!query) return tasks;
    return tasks.filter((task) => task.title.toLowerCase().includes(query));
  }, [tasks, titleFilter]);

  const tasksByStatus = useMemo(() => {
    const grouped = new Map<ProjectTaskStatus, ProjectTask[]>();
    for (const status of COLUMN_STATUSES) grouped.set(status, []);
    // The API already returns `sort_order, created_at, id` order.
    for (const task of filteredTasks) grouped.get(task.status)?.push(task);
    return grouped;
  }, [filteredTasks]);

  const visibleColumns = COLUMN_STATUSES.filter(
    (status) => showTerminal || !TERMINAL_STATUSES.includes(status),
  );

  const draggedTask = dragTaskId
    ? tasks.find((task) => task.task_id === dragTaskId) ?? null
    : null;

  const canDropInto = (status: ProjectTaskStatus): boolean =>
    canEdit &&
    draggedTask !== null &&
    draggedTask.status !== status &&
    isTransitionAllowed(draggedTask.status, status);

  const endDrag = () => {
    setDragTaskId(null);
    setOverStatus(null);
  };

  const moveTask = async (task: ProjectTask, status: ProjectTaskStatus) => {
    if (!canEdit || task.status === status) return;
    if (!isTransitionAllowed(task.status, status)) {
      message.warning(t("projects.boardDropInvalid"));
      return;
    }
    setPendingTaskId(task.task_id);
    try {
      await projectsApi.updateTask(projectId, task.task_id, { status });
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.boardMoveFailed"), t));
    } finally {
      // Re-read either way: the board only ever shows the server's state.
      await onChanged();
      setPendingTaskId(null);
    }
  };

  const handleCardDragStart = (
    event: DragEvent<HTMLDivElement>,
    task: ProjectTask,
  ) => {
    if (!canEdit || pendingTaskId === task.task_id) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData(TASK_DRAG_TYPE, task.task_id);
    event.dataTransfer.effectAllowed = "move";
    setDragTaskId(task.task_id);
  };

  const handleColumnDragOver = (
    event: DragEvent<HTMLDivElement>,
    status: ProjectTaskStatus,
  ) => {
    if (!draggedTask) return;
    if (![...event.dataTransfer.types].includes(TASK_DRAG_TYPE)) return;
    event.preventDefault();
    event.stopPropagation();
    const allowed = canDropInto(status);
    event.dataTransfer.dropEffect = allowed ? "move" : "none";
    // Kept for legal *and* illegal columns: the column styling decides which
    // feedback to show, so an illegal drop target is visibly rejected.
    setOverStatus(status);
  };

  const handleColumnDragLeave = (
    event: DragEvent<HTMLDivElement>,
    status: ProjectTaskStatus,
  ) => {
    // `dragleave` also bubbles out of the child cards; ignore those.
    const next = event.relatedTarget as Node | null;
    if (next && event.currentTarget.contains(next)) return;
    setOverStatus((current) => (current === status ? null : current));
  };

  const handleColumnDrop = (
    event: DragEvent<HTMLDivElement>,
    status: ProjectTaskStatus,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    const task = draggedTask;
    endDrag();
    if (!task || task.status === status) return;
    if (!isTransitionAllowed(task.status, status)) {
      message.warning(t("projects.boardDropInvalid"));
      return;
    }
    void moveTask(task, status);
  };

  const cancelAdd = () => {
    setAddingStatus(null);
    setNewTitle("");
  };

  const submitNewTask = async (status: ProjectTaskStatus) => {
    const title = newTitle.trim();
    if (!title || creating || !canEdit) return;
    setCreating(true);
    try {
      // The API only creates `todo` tasks; a card added to another legal
      // column is created first and then moved.
      const created = await projectsApi.createTask(projectId, { title });
      if (
        created.status !== status &&
        isTransitionAllowed(created.status, status)
      ) {
        try {
          await projectsApi.updateTask(projectId, created.task_id, { status });
        } catch (error) {
          message.error(
            apiErrorMessage(error, t("projects.boardMoveFailed"), t),
          );
        }
      }
      message.success(t("projects.boardCreated"));
      setNewTitle("");
      setAddingStatus(null);
    } catch (error) {
      message.error(apiErrorMessage(error, t("projects.boardCreateFailed"), t));
    } finally {
      setCreating(false);
      await onChanged();
    }
  };

  const openTimeline = (task: ProjectTask) => {
    setTimelineEvents([]);
    setTimelineTask(task);
  };

  const timelineItems = [...timelineEvents].reverse().map((event, index) => {
    const actionKey = TIMELINE_ACTION_KEYS[event.action];
    const from = asTaskStatus(event.payload.from);
    const to = asTaskStatus(event.payload.to);
    return {
      key: `${event.at}-${index}`,
      children: (
        <div className={styles.timelineItem}>
          <Text strong>{actionKey ? t(actionKey) : event.action}</Text>
          {from && to ? (
            <Text type="secondary" className={styles.timelineDetail}>
              {`${t(STATUS_LABEL_KEYS[from])} → ${t(STATUS_LABEL_KEYS[to])}`}
            </Text>
          ) : null}
          <Text type="secondary" className={styles.timelineMeta}>
            {`${event.actor} · ${formatServerDateTime(event.at, timeZone)}`}
          </Text>
        </div>
      ),
    };
  });

  const renderCard = (task: ProjectTask) => {
    const pending = pendingTaskId === task.task_id;
    const dragging = dragTaskId === task.task_id;
    const cardClass = [
      styles.card,
      dragging ? styles.cardDragging : "",
      pending ? styles.cardPending : "",
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <div
        key={task.task_id}
        className={cardClass}
        draggable={canEdit && !pending}
        onDragStart={(event) => handleCardDragStart(event, task)}
        onDragEnd={endDrag}
      >
        <div className={styles.cardHeader}>
          <Text strong className={styles.cardTitle}>
            {task.title}
          </Text>
          <Tooltip title={t("projects.taskPriority")}>
            <Tag className={styles.cardPriority}>{task.priority}</Tag>
          </Tooltip>
        </div>
        <div className={styles.cardMeta}>
          {task.assignee_type && task.assignee_id ? (
            <span className={styles.cardMetaItem}>
              <User size={12} />
              <Text type="secondary" className={styles.cardMetaText}>
                {`${task.assignee_type}:${task.assignee_id}`}
              </Text>
            </span>
          ) : null}
          {task.due_at ? (
            <span className={styles.cardMetaItem}>
              <CalendarDays size={12} />
              <Text type="secondary" className={styles.cardMetaText}>
                {formatServerDateTime(task.due_at, timeZone)}
              </Text>
            </span>
          ) : null}
        </div>
        <div className={styles.cardFooter}>
          {canEdit ? (
            <Select<ProjectTaskStatus>
              size="small"
              className={styles.cardStatusSelect}
              value={task.status}
              loading={pending}
              aria-label={t("projects.taskStatus")}
              onChange={(status) => void moveTask(task, status)}
              options={[task.status, ...STATUS_TRANSITIONS[task.status]].map(
                (status) => ({
                  value: status,
                  label: t(STATUS_LABEL_KEYS[status]),
                }),
              )}
            />
          ) : (
            <Tag color={STATUS_COLORS[task.status]}>
              {t(STATUS_LABEL_KEYS[task.status])}
            </Tag>
          )}
          <Tooltip title={t("projects.boardTimeline")}>
            <Button
              type="text"
              size="small"
              aria-label={t("projects.boardTimeline")}
              icon={<History size={14} />}
              onClick={() => openTimeline(task)}
            />
          </Tooltip>
        </div>
      </div>
    );
  };

  const renderColumn = (status: ProjectTaskStatus) => {
    const columnTasks = tasksByStatus.get(status) ?? [];
    // The column the dragged card came from is neither locked nor rejected.
    const isOrigin = draggedTask?.status === status;
    const droppable = canDropInto(status);
    const columnClass = [
      styles.column,
      draggedTask && !droppable && !isOrigin ? styles.columnLocked : "",
      overStatus === status && !isOrigin
        ? droppable
          ? styles.columnOver
          : styles.columnReject
        : "",
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <div
        key={status}
        className={columnClass}
        onDragOver={(event) => handleColumnDragOver(event, status)}
        onDragLeave={(event) => handleColumnDragLeave(event, status)}
        onDrop={(event) => handleColumnDrop(event, status)}
      >
        <div className={styles.columnHeader}>
          <Tag color={STATUS_COLORS[status]}>
            {t(STATUS_LABEL_KEYS[status])}
          </Tag>
          <span className={styles.columnCount}>{columnTasks.length}</span>
        </div>
        <div className={styles.columnBody}>
          {columnTasks.length === 0 ? (
            <div className={styles.columnEmpty}>{t("projects.tasksEmpty")}</div>
          ) : (
            columnTasks.map(renderCard)
          )}
        </div>
        {canEdit ? (
          addingStatus === status ? (
            <div className={styles.addForm}>
              <Input
                size="small"
                autoFocus
                maxLength={120}
                value={newTitle}
                disabled={creating}
                placeholder={t("projects.boardAddPlaceholder")}
                aria-label={t("projects.boardAddPlaceholder")}
                onChange={(event) => setNewTitle(event.target.value)}
                onPressEnter={() => void submitNewTask(status)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") cancelAdd();
                }}
              />
              <Button
                type="text"
                size="small"
                aria-label={t("common.save")}
                disabled={!newTitle.trim()}
                loading={creating}
                icon={<Check size={14} />}
                onClick={() => void submitNewTask(status)}
              />
              <Button
                type="text"
                size="small"
                aria-label={t("common.cancel")}
                icon={<X size={14} />}
                onClick={cancelAdd}
              />
            </div>
          ) : (
            <Tooltip
              title={
                canCreateInto(status)
                  ? t("projects.boardAdd")
                  : t("projects.boardAddBlocked")
              }
            >
              <Button
                type="text"
                size="small"
                block
                className={styles.addButton}
                icon={<Plus size={14} />}
                onClick={() => {
                  if (!canCreateInto(status)) {
                    message.warning(t("projects.boardAddBlocked"));
                    return;
                  }
                  setNewTitle("");
                  setAddingStatus(status);
                }}
              >
                {t("projects.boardAdd")}
              </Button>
            </Tooltip>
          )
        ) : null}
      </div>
    );
  };

  return (
    <div className={styles.board}>
      <div className={styles.toolbar}>
        <Input
          size="small"
          allowClear
          className={styles.search}
          value={titleFilter}
          prefix={<Search size={14} />}
          placeholder={t("projects.boardSearchPlaceholder")}
          aria-label={t("projects.boardSearchPlaceholder")}
          onChange={(event) => setTitleFilter(event.target.value)}
        />
        <Checkbox
          checked={showTerminal}
          onChange={(event) => setShowTerminal(event.target.checked)}
        >
          {t("projects.boardShowTerminal")}
        </Checkbox>
        {!canEdit ? (
          <Text type="secondary" className={styles.readOnly}>
            {t("projects.boardReadOnly")}
          </Text>
        ) : null}
      </div>
      <div className={styles.columns}>{visibleColumns.map(renderColumn)}</div>
      <Modal
        open={timelineTask !== null}
        title={t("projects.boardTimelineTitle", {
          title: timelineTask?.title ?? "",
        })}
        footer={null}
        destroyOnHidden
        onCancel={() => setTimelineTask(null)}
      >
        {timelineLoading ? (
          <div className={styles.timelineCentered}>
            <Spin />
          </div>
        ) : timelineError ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={apiErrorMessage(
              timelineError,
              t("projects.boardTimelineLoadFailed"),
              t,
            )}
          />
        ) : timelineItems.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t("projects.boardTimelineEmpty")}
          />
        ) : (
          <Timeline items={timelineItems} />
        )}
      </Modal>
    </div>
  );
}

export default Board;
