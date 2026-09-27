import { useMemo, useState } from "react";
import { Input, Select, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useTranslation } from "react-i18next";

import {
  projectsApi,
  type ProjectTask,
  type ProjectTaskStatus,
} from "../../../api/modules/projects";
import { EmptyState } from "../../../components/EmptyState";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import {
  COLUMN_STATUSES,
  STATUS_COLORS,
  STATUS_LABEL_KEYS,
} from "../utils/taskStatus";
import styles from "./TaskListView.module.less";

/**
 * Task list view — the `tasks` tab (PLAN.md §9).
 *
 * The board is the only other place that renders a task set; this view shares
 * its status vocabulary through `utils/taskStatus.ts` and never re-declares a
 * label / colour / column map of its own.
 *
 * Data is self-owned (`projectsApi.listTasks`) and unpaginated: the backend
 * `list_tasks` has no limit and a project's task count is bounded.
 */

const DASH = "—";

export interface TaskListViewProps {
  projectId: string;
  /** Open the existing task detail / dialog entry point. */
  onOpenTask: (taskId: string) => void;
  /** Bumped by the parent after any task write to trigger a re-read. */
  refreshKey?: number;
}

/**
 * S7 (PLAN §9): `sort_order` ascending, ties broken by `task_id` ascending.
 * Deliberately not `Array#sort` stability plus backend order — the comparator is
 * total, so the rendering order is deterministic for equal `sort_order` too.
 */
function bySortOrderThenTaskId(a: ProjectTask, b: ProjectTask): number {
  if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
  if (a.task_id === b.task_id) return 0;
  return a.task_id < b.task_id ? -1 : 1;
}

function assigneeLabel(task: ProjectTask): string {
  if (!task.assignee_type || !task.assignee_id) return DASH;
  return `${task.assignee_type}:${task.assignee_id}`;
}

export default function TaskListView({
  projectId,
  onOpenTask,
  refreshKey,
}: TaskListViewProps): JSX.Element {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [statuses, setStatuses] =
    useState<ProjectTaskStatus[]>(COLUMN_STATUSES);
  const [keyword, setKeyword] = useState("");

  const { data: tasks, loading } = useAsyncResource<ProjectTask[]>(
    [],
    () => projectsApi.listTasks(projectId),
    [projectId, refreshKey],
    {
      t,
      errorFallback: t("projects.loadFailed"),
      logLabel: "project-task-list",
    },
  );

  const rows = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    return [...tasks]
      .filter((task) => statuses.includes(task.status))
      .filter(
        (task) =>
          needle === "" ||
          `${task.title}\n${task.description}`.toLowerCase().includes(needle),
      )
      .sort(bySortOrderThenTaskId);
  }, [tasks, statuses, keyword]);

  const columns: ColumnsType<ProjectTask> = [
    {
      title: t("projects.taskListColumnStatus"),
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (status: ProjectTaskStatus) => (
        <Tag color={STATUS_COLORS[status]}>{t(STATUS_LABEL_KEYS[status])}</Tag>
      ),
    },
    {
      title: t("projects.taskListColumnTitle"),
      dataIndex: "title",
      key: "title",
      render: (title: string, task) => (
        <button
          type="button"
          className={styles.titleLink}
          onClick={() => onOpenTask(task.task_id)}
        >
          {title}
        </button>
      ),
    },
    {
      title: t("projects.taskListColumnAssignee"),
      key: "assignee",
      width: 170,
      render: (_, task) => assigneeLabel(task),
    },
    {
      title: t("projects.taskListColumnPriority"),
      dataIndex: "priority",
      key: "priority",
      width: 90,
    },
    {
      title: t("projects.taskListColumnStartAt"),
      dataIndex: "start_at",
      key: "start_at",
      width: 170,
      render: (startAt: number | null) =>
        formatServerDateTime(startAt ?? 0, timeZone),
    },
    {
      title: t("projects.taskListColumnDueAt"),
      dataIndex: "due_at",
      key: "due_at",
      width: 170,
      render: (dueAt: number | null) =>
        formatServerDateTime(dueAt ?? 0, timeZone),
    },
    {
      title: t("projects.taskListColumnTags"),
      key: "tags",
      render: (_, task) =>
        task.tags?.length ? (
          <Space size={4} wrap>
            {task.tags.map((tag) => (
              <Tag key={tag.tag_id} color={tag.color || undefined}>
                {tag.name}
              </Tag>
            ))}
          </Space>
        ) : (
          DASH
        ),
    },
    {
      title: t("projects.taskListColumnUpdatedAt"),
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (updatedAt: number) => formatServerDateTime(updatedAt, timeZone),
    },
  ];

  return (
    <div className={styles.wrapper} data-testid="project-task-list">
      <div className={styles.toolbar}>
        <span className={styles.title}>{t("projects.taskListTitle")}</span>
        <Select<ProjectTaskStatus[]>
          mode="multiple"
          className={styles.statusFilter}
          aria-label={t("projects.taskListFilterStatus")}
          value={statuses}
          onChange={setStatuses}
          maxTagCount="responsive"
          options={COLUMN_STATUSES.map((status) => ({
            value: status,
            label: t(STATUS_LABEL_KEYS[status]),
          }))}
        />
        <Input
          className={styles.keyword}
          allowClear
          value={keyword}
          placeholder={t("projects.taskListFilterKeyword")}
          aria-label={t("projects.taskListFilterKeyword")}
          onChange={(event) => setKeyword(event.target.value)}
        />
      </div>

      {rows.length === 0 && !loading ? (
        <EmptyState variant="empty" title={t("projects.taskListEmpty")} />
      ) : (
        <Table<ProjectTask>
          rowKey="task_id"
          size="small"
          className={styles.table}
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
          scroll={{ x: 1020 }}
        />
      )}
    </div>
  );
}
