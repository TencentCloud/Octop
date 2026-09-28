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
  Send,
  User,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  projectsApi,
  type ProjectCustomFieldType,
  type ProjectCustomFieldWriteValue,
  type ProjectTask,
  type ProjectTaskStatus,
  type ProjectTimelineEvent,
} from "../../../api/modules/projects";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "../../../utils/antdMessage";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import {
  asTaskStatus,
  COLUMN_STATUSES,
  isTransitionAllowed,
  STATUS_COLORS,
  STATUS_LABEL_KEYS,
  STATUS_TRANSITIONS,
  TERMINAL_STATUSES,
} from "../utils/taskStatus";
import TaskCreateModal from "./TaskCreateModal";
import styles from "./Board.module.less";

const { Text } = Typography;

/** Custom drag type: identifies a board card during a native HTML5 drag. */
const TASK_DRAG_TYPE = "application/x-octop-project-task";

/** Timeline actions recorded by the backend (`infra/db/repos/project_tasks.py`). */
const TIMELINE_ACTION_KEYS: Record<string, string> = {
  "task.created": "projects.boardActionCreated",
  "task.updated": "projects.boardActionUpdated",
  "task.status_changed": "projects.boardActionStatusChanged",
  "task.assigned": "projects.boardActionAssigned",
  "task.deleted": "projects.boardActionDeleted",
  "task.dispatched": "projects.boardActionDispatched",
};

/** Every column can be created into directly (R2; the old todo-only limit is gone). */
function canCreateInto(status: ProjectTaskStatus): boolean {
  return (COLUMN_STATUSES as string[]).includes(status);
}

interface BoardProps {
  projectId: string;
  tasks: ProjectTask[];
  /** Archived projects and viewers get a read-only board (no drag, no writes). */
  canEdit: boolean;
  /** Re-read the project tasks after a write so the board mirrors the server. */
  onChanged: () => void | Promise<void>;
}

/** Unix seconds in, server-timezone text out (PLAN §0 invariant 3). */
function formatCustomFieldValue(
  value: ProjectCustomFieldWriteValue | undefined,
  type: ProjectCustomFieldType | undefined,
  timeZone: string,
): string {
  if (value === null || value === undefined || value === "") return "";
  if (type === "date") {
    const seconds = Number(value);
    return Number.isFinite(seconds) && seconds > 0
      ? formatServerDateTime(seconds, timeZone)
      : "";
  }
  return String(value);
}

/** Tags + custom-field values under a card's meta row (AC-U-13 / AC-CF-5). */
function CardMetadata({
  task,
  timeZone,
}: {
  task: ProjectTask;
  timeZone: string;
}) {
  const tags = task.tags ?? [];
  const fields = (task.custom_fields ?? []).filter(
    (field) => formatCustomFieldValue(field.value, field.type, timeZone) !== "",
  );
  if (tags.length === 0 && fields.length === 0) return null;
  return (
    <div className={styles.cardMetadata}>
      {tags.map((tag) => (
        <Tag
          key={tag.tag_id}
          color={tag.color || undefined}
          className={styles.cardTag}
        >
          {tag.name}
        </Tag>
      ))}
      {fields.map((field) => (
        <span key={field.field_id} className={styles.cardMetaItem}>
          <Text type="secondary" className={styles.cardMetaText}>
            {`${field.label}：${formatCustomFieldValue(
              field.value,
              field.type,
              timeZone,
            )}`}
          </Text>
        </span>
      ))}
    </div>
  );
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
  /** Task whose explicit dispatch action is in flight (PLAN §8.1-2). */
  const [dispatchingTaskId, setDispatchingTaskId] = useState<string | null>(
    null,
  );
  const [addingStatus, setAddingStatus] = useState<ProjectTaskStatus | null>(
    null,
  );
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  /** Full create dialog (R3); the column "+" keeps the inline quick path (R5). */
  const [createOpen, setCreateOpen] = useState(false);
  /**
   * Column whose header "+" opened the dialog: its status is prefilled through
   * the dialog's existing ``initialValues`` (PLAN §3 — no prop change there).
   * ``null`` = opened from the toolbar, i.e. the dialog's own default status.
   */
  const [createStatus, setCreateStatus] = useState<ProjectTaskStatus | null>(
    null,
  );
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

  /**
   * Explicit dispatch action (PLAN §8.1-2). The create dialog only writes
   * `assignee`; this is where the task is actually handed to the agent/team.
   */
  const dispatchTaskToAssignee = async (task: ProjectTask) => {
    if (!canEdit || dispatchingTaskId) return;
    setDispatchingTaskId(task.task_id);
    try {
      await projectsApi.dispatchTask(projectId, task.task_id);
      message.success(t("projects.boardActionDispatched"));
    } catch (error) {
      message.error(
        apiErrorMessage(error, t("apiErrors.PROJECT_TASK_DISPATCH_INVALID"), t),
      );
    } finally {
      setDispatchingTaskId(null);
      // Re-read either way: dispatch changes `thread_id` server-side.
      await onChanged();
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
      // One request carrying the target column (R2): the old
      // "create as todo, then move" two-step is gone.
      await projectsApi.createTask(projectId, { title, status });
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
    // PLAN §8.1-3: only an agent / team assignee has a runtime to dispatch to.
    const canDispatch =
      task.assignee_type === "agent" || task.assignee_type === "team";
    const dispatchTitle = canDispatch
      ? t("projects.boardDispatch")
      : t("apiErrors.PROJECT_TASK_DISPATCH_INVALID");
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
          {task.start_at ? (
            <span className={styles.cardMetaItem}>
              <CalendarDays size={12} />
              <Text type="secondary" className={styles.cardMetaText}>
                {formatServerDateTime(task.start_at, timeZone)}
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
        <CardMetadata task={task} timeZone={timeZone} />
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
          <div className={styles.cardActions}>
            {canEdit ? (
              <Tooltip title={dispatchTitle}>
                <Button
                  type="text"
                  size="small"
                  className={styles.cardDispatch}
                  aria-label={t("projects.boardDispatch")}
                  title={dispatchTitle}
                  disabled={!canDispatch || pending}
                  loading={dispatchingTaskId === task.task_id}
                  icon={<Send size={14} />}
                  onClick={() => void dispatchTaskToAssignee(task)}
                />
              </Tooltip>
            ) : null}
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
          {canEdit ? (
            /* Second entry point (PLAN §3): the full dialog, prefilled with this
               column's status. The inline quick create below stays untouched —
               the two coexist on purpose (R5).
               The accessible name repeats the column so the seven identical
               "+ Add task" buttons stay distinguishable for screen readers. */
            <Button
              type="text"
              size="small"
              style={{ marginInlineStart: "auto" }}
              icon={<Plus size={14} />}
              aria-label={`${t("projects.boardAdd")} · ${t(
                STATUS_LABEL_KEYS[status],
              )}`}
              data-testid={`board-column-add-${status}`}
              onClick={() => {
                setCreateStatus(status);
                setCreateOpen(true);
              }}
            >
              {t("projects.boardAdd")}
            </Button>
          ) : null}
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
            <Button
              type="text"
              size="small"
              block
              className={styles.addButton}
              icon={<Plus size={14} />}
              disabled={!canCreateInto(status)}
              onClick={() => {
                setNewTitle("");
                setAddingStatus(status);
              }}
            >
              {t("projects.boardAdd")}
            </Button>
          )
        ) : null}
      </div>
    );
  };

  return (
    <div className={styles.board}>
      <div className={styles.toolbar}>
        {canEdit ? (
          <Button
            type="primary"
            size="small"
            icon={<Plus size={14} />}
            onClick={() => {
              // Toolbar entry keeps the dialog's own default status: without
              // this reset it would inherit the last column that was used.
              setCreateStatus(null);
              setCreateOpen(true);
            }}
          >
            {t("projects.createTaskSubmit")}
          </Button>
        ) : null}
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
      <TaskCreateModal
        open={createOpen}
        projectId={projectId}
        tasks={tasks}
        canEdit={canEdit}
        /* Only the column entry prefills; ``initialValues`` is read once per
           open by the dialog, so the status is already correct on the first
           render after the click. */
        initialValues={createStatus ? { status: createStatus } : undefined}
        onClose={() => setCreateOpen(false)}
        onCreated={onChanged}
      />
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
