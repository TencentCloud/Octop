import { useMemo, useState } from "react";
import { Input, Select, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  projectsApi,
  type ProjectTask,
  type ProjectTaskStatus,
} from "../../../api/modules/projects";
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
 * Task list view — the `tasks` tab (PLAN.md §9 / §1 F1)。
 *
 * 平表改为**按状态分区**：7 个区块恒显（顺序 = `COLUMN_STATUSES`）、空区显示
 * `taskListEmpty`、筛选**只减少区内行**。分区行与任务行共用**同一张表**，因此
 * 列面仍冻结为 **8 列**（§5.3 机判 ①：`within(getByRole("table"))` 单表 + 8 表头）；
 * 行内编辑入口放进既有「标题」单元格，**不新增列**。
 *
 * 状态词表唯一来源 = `utils/taskStatus.ts`（本文件不得另立映射）。
 */

const DASH = "—";

/**
 * 列面契约（8 列，顺序即表头顺序）。测试用**字面量**独立断言，不从这里推导；
 * 此导出仅供「渲染列数 ↔ 列面」对照（§5.3 机判 ③ 的对照面）。
 */
export const TASK_LIST_COLUMN_KEYS = [
  "projects.taskListColumnStatus",
  "projects.taskListColumnTitle",
  "projects.taskListColumnAssignee",
  "projects.taskListColumnPriority",
  "projects.taskListColumnStartAt",
  "projects.taskListColumnDueAt",
  "projects.taskListColumnTags",
  "projects.taskListColumnUpdatedAt",
] as const;

export interface TaskListViewProps {
  projectId: string;
  /**
   * 任务详情入口。**本轮不渲染交互**（详情页属第四批）——契约保留、仍由父层
   * 传入，第四批接线时直接启用。
   */
  onOpenTask?: (taskId: string) => void;
  /** Bumped by the parent after any task write to trigger a re-read. */
  refreshKey?: number;
  /** 传入才渲染行内编辑入口（§5.3 G9 (a)：不新增列）。 */
  onEditTask?: (taskId: string) => void;
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

/** 一行 = 区块标题 / 空区提示 / 任务。三者共用同一张表的列面。 */
type ListRow =
  | { key: string; kind: "section"; status: ProjectTaskStatus; count: number }
  | { key: string; kind: "empty"; status: ProjectTaskStatus }
  | { key: string; kind: "task"; status: ProjectTaskStatus; task: ProjectTask };

export default function TaskListView({
  projectId,
  refreshKey,
  onEditTask,
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

  /**
   * 分区结构（PLAN §1.1/§1.2 冻结）：
   * - **7 区恒显**，顺序 = `COLUMN_STATUSES`；筛选只减少区内行，**不隐藏空区**；
   * - 空区插入一行空态（复用 `taskListEmpty`，不新增键）；
   * - 区内排序复用全序比较器 `(sort_order, task_id)`。
   */
  const rows = useMemo(() => {
    const needle = keyword.trim().toLowerCase();
    const matches = (task: ProjectTask) =>
      statuses.includes(task.status) &&
      (needle === "" ||
        `${task.title}\n${task.description}`.toLowerCase().includes(needle));

    const out: ListRow[] = [];
    for (const status of COLUMN_STATUSES) {
      const zone = tasks
        .filter((task) => task.status === status && matches(task))
        .sort(bySortOrderThenTaskId);
      out.push({
        key: `section-${status}`,
        kind: "section",
        status,
        count: zone.length,
      });
      if (zone.length === 0) {
        out.push({ key: `empty-${status}`, kind: "empty", status });
        continue;
      }
      for (const task of zone) {
        out.push({ key: task.task_id, kind: "task", status, task });
      }
    }
    return out;
  }, [tasks, statuses, keyword]);

  const isTaskRow = (row: ListRow): row is Extract<ListRow, { kind: "task" }> =>
    row.kind === "task";
  /** 区块行 / 空区行横跨 8 列；任务行正常分列。 */
  const spanAll = (row: ListRow) => (isTaskRow(row) ? {} : { colSpan: 8 });
  const spanNone = (row: ListRow) => (isTaskRow(row) ? {} : { colSpan: 0 });

  const columns: ColumnsType<ListRow> = [
    {
      title: t("projects.taskListColumnStatus"),
      key: "status",
      width: 110,
      onCell: spanAll,
      render: (_, row) => {
        if (row.kind === "section") {
          return (
            <div className={styles.sectionHeader}>
              <Tag color={STATUS_COLORS[row.status]}>
                <span
                  data-testid={`task-section-title-${row.status}`}
                  className={styles.sectionTitle}
                >
                  {t(STATUS_LABEL_KEYS[row.status])}
                </span>
              </Tag>
              <span
                data-testid={`task-section-count-${row.status}`}
                className={styles.sectionCount}
              >
                {row.count}
              </span>
            </div>
          );
        }
        if (row.kind === "empty") {
          return (
            <span
              data-testid={`task-section-empty-${row.status}`}
              className={styles.sectionEmpty}
            >
              {t("projects.taskListEmpty")}
            </span>
          );
        }
        return (
          <Tag color={STATUS_COLORS[row.status]}>
            {t(STATUS_LABEL_KEYS[row.status])}
          </Tag>
        );
      },
    },
    {
      title: t("projects.taskListColumnTitle"),
      key: "title",
      onCell: spanNone,
      render: (_, row) =>
        isTaskRow(row) ? (
          <span className={styles.titleCell}>
            {/* S8(b)：标题是纯文本（无 onClick、不是 button）。 */}
            <span
              className={styles.titleText}
              data-testid={`task-row-title-${row.task.task_id}`}
            >
              {row.task.title}
            </span>
            {onEditTask ? (
              <Tooltip title={t("projects.editTaskTitle")}>
                <button
                  type="button"
                  className={styles.editButton}
                  data-testid={`task-row-edit-${row.task.task_id}`}
                  aria-label={t("projects.editTaskTitle")}
                  onClick={() => onEditTask(row.task.task_id)}
                >
                  <Pencil size={14} aria-hidden />
                </button>
              </Tooltip>
            ) : null}
          </span>
        ) : null,
    },
    {
      title: t("projects.taskListColumnAssignee"),
      key: "assignee",
      width: 170,
      onCell: spanNone,
      render: (_, row) => (isTaskRow(row) ? assigneeLabel(row.task) : null),
    },
    {
      title: t("projects.taskListColumnPriority"),
      key: "priority",
      width: 90,
      onCell: spanNone,
      render: (_, row) => (isTaskRow(row) ? row.task.priority : null),
    },
    {
      title: t("projects.taskListColumnStartAt"),
      key: "start_at",
      width: 170,
      onCell: spanNone,
      render: (_, row) =>
        isTaskRow(row)
          ? formatServerDateTime(row.task.start_at ?? 0, timeZone)
          : null,
    },
    {
      title: t("projects.taskListColumnDueAt"),
      key: "due_at",
      width: 170,
      onCell: spanNone,
      render: (_, row) =>
        isTaskRow(row)
          ? formatServerDateTime(row.task.due_at ?? 0, timeZone)
          : null,
    },
    {
      title: t("projects.taskListColumnTags"),
      key: "tags",
      onCell: spanNone,
      render: (_, row) =>
        isTaskRow(row) ? (
          row.task.tags?.length ? (
            <Space size={4} wrap>
              {row.task.tags.map((tag) => (
                <Tag key={tag.tag_id} color={tag.color || undefined}>
                  {tag.name}
                </Tag>
              ))}
            </Space>
          ) : (
            DASH
          )
        ) : null,
    },
    {
      title: t("projects.taskListColumnUpdatedAt"),
      key: "updated_at",
      width: 180,
      onCell: spanNone,
      render: (_, row) =>
        isTaskRow(row)
          ? formatServerDateTime(row.task.updated_at, timeZone)
          : null,
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

      <Table<ListRow>
        rowKey="key"
        size="small"
        className={styles.table}
        loading={loading}
        columns={columns}
        dataSource={rows}
        pagination={false}
        scroll={{ x: 1020 }}
        onRow={(row) => {
          if (row.kind === "section") {
            return {
              "data-testid": `task-section-${row.status}`,
              "data-section": row.status,
            } as React.HTMLAttributes<HTMLElement>;
          }
          if (row.kind === "empty") {
            return {
              "data-testid": `task-section-empty-row-${row.status}`,
              "data-section": row.status,
            } as React.HTMLAttributes<HTMLElement>;
          }
          return {
            "data-testid": `task-row-${row.task.task_id}`,
            "data-section": row.status,
          } as React.HTMLAttributes<HTMLElement>;
        }}
      />
    </div>
  );
}
