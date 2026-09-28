import type { ProjectTaskStatus } from "../../../api/modules/projects";

/**
 * 任务状态映射的**唯一来源**（PLAN.md §9「状态映射单一来源」）。
 *
 * `Board.tsx`（由 T-FE-TASKS 改为 import）与 `TaskListView` 都只能从这里取，
 * **不得**复制第二份；词表与邻接的权威是 `PLAN.md §1.1/§1.2`。
 */

/** 看板列序：planning 最前，既有 6 值相对序逐字保留（PLAN §1.1）。 */
export const COLUMN_STATUSES: ProjectTaskStatus[] = [
  "planning",
  "todo",
  "doing",
  "review",
  "blocked",
  "done",
  "cancelled",
];

/**
 * 终态列（S-1 冻结）：`planning` **不进**终态，因此「显示已完成/已取消」
 * 开关只过滤本集合，planning 列恒显于列首。
 */
export const TERMINAL_STATUSES: ProjectTaskStatus[] = ["done", "cancelled"];

/** i18n 键名（值由 `dashboard/src/locales/**` 提供，本文件不持有文案）。 */
export const STATUS_LABEL_KEYS: Record<ProjectTaskStatus, string> = {
  planning: "projects.taskStatusPlanning",
  todo: "projects.taskStatusTodo",
  doing: "projects.taskStatusDoing",
  review: "projects.taskStatusReview",
  blocked: "projects.taskStatusBlocked",
  done: "projects.taskStatusDone",
  cancelled: "projects.taskStatusCancelled",
};

/** antd `Tag` 的 color 值。 */
export const STATUS_COLORS: Record<ProjectTaskStatus, string> = {
  planning: "default",
  todo: "default",
  doing: "processing",
  review: "warning",
  blocked: "error",
  done: "success",
  cancelled: "default",
};

/**
 * 与 `infra/projects/service.py` 的 `_TASK_TRANSITIONS` 同构（PLAN §1.2）。
 * 后端仍是权威：非法流转由后端回 `PROJECT_TASK_STATUS_INVALID`（409）；
 * 这里的判定只用于「不发出必然失败的请求」。
 */
export const STATUS_TRANSITIONS: Record<
  ProjectTaskStatus,
  ProjectTaskStatus[]
> = {
  planning: ["todo", "cancelled"],
  todo: ["planning", "doing", "blocked", "cancelled"],
  doing: ["todo", "review", "done", "blocked", "cancelled"],
  review: ["doing", "done", "blocked", "cancelled"],
  blocked: ["todo", "doing", "cancelled"],
  done: ["doing"],
  cancelled: [],
};

/** 把任意值收敛为合法任务状态；未知值（含历史事件 payload）返回 `null`。 */
export function asTaskStatus(value: unknown): ProjectTaskStatus | null {
  return typeof value === "string" &&
    (COLUMN_STATUSES as string[]).includes(value)
    ? (value as ProjectTaskStatus)
    : null;
}

/** 状态机邻接判定（纯派生，数据仍只在本文件的 `STATUS_TRANSITIONS`）。 */
export function isTransitionAllowed(
  from: ProjectTaskStatus,
  to: ProjectTaskStatus,
): boolean {
  return STATUS_TRANSITIONS[from].includes(to);
}
