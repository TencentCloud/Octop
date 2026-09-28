import { useState } from "react";
import { Descriptions, Space, Spin, Tag, Tooltip } from "antd";
import { ArrowLeft, Download, Paperclip, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  type ProjectAttachment,
  type ProjectTask,
  projectsApi,
} from "../../../api/modules/projects";
import { projectMetadataApi } from "../../../api/modules/projectMetadata";
import { useServerTimezone } from "../../../hooks/useServerTimezone";
import { formatServerDateTime } from "../../../utils/formatMessageTime";
import { STATUS_COLORS, STATUS_LABEL_KEYS } from "../utils/taskStatus";
import TaskCreateModal, {
  type TaskCreateValues,
  type TaskPatchValues,
} from "./TaskCreateModal";
import styles from "./TaskDetailPanel.module.less";

/**
 * 任务详情面板（PLAN §4 / G4）。
 *
 * 数据来源 = **路径 ①**（`PLAN §4.2`）：**只用已加载的列表数据**（`task` prop），
 * **不新增单任务 GET**。未命中（`task === undefined` 且非 loading）→ `taskDetailNotFound`
 * 优雅降级，绝不白屏。
 *
 * 编辑 = 复用批次三的 `TaskCreateModal(mode="edit")`（**同一份字段定义 + 差异提交**），
 * 保存成功后 `onChanged()` 重读（非本地乐观）。
 *
 * 「过程」区 = `PLAN §4.3` 的**最小只读轨迹**（⚠️ 诚实边界：**不是**完整状态流转历史）。
 * 本轮可得的事实只有 4 类：**创建 `created_at` / 当前状态 / 最近更新 `updated_at` /
 * 有 `thread_id` 时「已派单」** —— 完整历史需要任务事件表或单任务 GET（路径 ②），
 * **本轮不做**，故这里只呈现上述由 `TaskOut` 可派生的事实。
 */

const DASH = "—";

export interface TaskDetailPanelProps {
  projectId: string;
  /** 已加载列表里的那条任务；未命中（不存在 / 已删除 / 深链未取到）→ undefined。 */
  task?: ProjectTask;
  /** owner 为深链触发的一次列表重取进行中；true 时不显示「不存在」。 */
  loading?: boolean;
  /** 写权限（`PROJECT_WRITE` = member+）；viewer → 无编辑入口。 */
  canEdit: boolean;
  /** 同项目任务（编辑弹窗的父任务来源；与列表同一份数据，不新增读取环）。 */
  tasks: ProjectTask[];
  /** 返回列表（owner 移除 `?task=`，保留 `tab=tasks`）。 */
  onBack: () => void;
  /** 保存成功后重读（owner 的 load()）。 */
  onChanged: () => void | Promise<void>;
}

/**
 * 进入判据（`PLAN §4.1` 冻结）：**有 `task` 参数即以详情为准** —— 缺 `tab` 参数时
 * 同样进详情（`?task=<id>` 隐含 tasks 详情），URL 的 `tab` 解析仍归 owner。
 */
export function hasTaskDetailParam(params: URLSearchParams): boolean {
  const taskId = params.get("task");
  return taskId !== null && taskId !== "";
}

function taskToValues(task: ProjectTask): TaskCreateValues {
  return {
    task_id: task.task_id,
    title: task.title,
    description: task.description,
    status: task.status,
    priority: task.priority,
    assignee:
      task.assignee_type && task.assignee_id
        ? { type: task.assignee_type, id: task.assignee_id }
        : null,
    tag_ids: (task.tags ?? []).map((tag) => tag.tag_id),
    start_at: task.start_at,
    due_at: task.due_at,
    parent_id: task.parent_id,
    deps: task.deps ?? [],
    custom_fields: Object.fromEntries(
      (task.custom_fields ?? []).map((field) => [field.field_id, field.value]),
    ),
  };
}

export default function TaskDetailPanel({
  projectId,
  task,
  loading = false,
  canEdit,
  tasks,
  onBack,
  onChanged,
}: TaskDetailPanelProps): JSX.Element {
  const { t } = useTranslation();
  const timeZone = useServerTimezone();
  const [editing, setEditing] = useState(false);

  /** 附件只读下载：走**既有**端点，不新增上传/删除路径（`AC-G4-5`）。 */
  const download = async (attachment: ProjectAttachment) => {
    const blob = await projectMetadataApi.downloadAttachment(
      projectId,
      attachment.artifact_id,
    );
    // jsdom 无 createObjectURL；真实浏览器里触发一次下载。
    if (typeof URL.createObjectURL !== "function") return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = attachment.name;
    link.click();
    URL.revokeObjectURL(url);
  };

  const submitEdit = async (patch: TaskPatchValues) => {
    if (!task) return;
    await projectsApi.updateTask(projectId, task.task_id, patch);
    await onChanged();
  };

  const parent = task?.parent_id
    ? tasks.find((item) => item.task_id === task.parent_id)
    : undefined;

  return (
    <div className={styles.panel} data-testid="task-detail-panel">
      <div className={styles.header}>
        <button
          type="button"
          className={styles.back}
          data-testid="task-detail-back"
          onClick={onBack}
        >
          <ArrowLeft size={14} aria-hidden />
          {t("projects.taskDetailBack")}
        </button>
        <span className={styles.headerTitle}>
          {t("projects.taskDetailTitle")}
        </span>
        {canEdit && task ? (
          <button
            type="button"
            className={styles.edit}
            data-testid="task-detail-edit"
            onClick={() => setEditing(true)}
          >
            <Pencil size={14} aria-hidden />
            {t("projects.editTaskTitle")}
          </button>
        ) : null}
      </div>

      {!task ? (
        loading ? (
          <div className={styles.loading} data-testid="task-detail-loading">
            <Spin size="small" />
          </div>
        ) : (
          <div className={styles.notFound} data-testid="task-detail-not-found">
            {t("projects.taskDetailNotFound")}
          </div>
        )
      ) : (
        <>
          <div className={styles.titleRow}>
            <h3 className={styles.title} data-testid="task-detail-title">
              {task.title}
            </h3>
            <Tag color={STATUS_COLORS[task.status]}>
              {t(STATUS_LABEL_KEYS[task.status])}
            </Tag>
          </div>

          <Descriptions column={2} size="small" className={styles.meta}>
            <Descriptions.Item label={t("projects.taskListColumnStatus")}>
              <span data-testid="task-detail-status">
                {t(STATUS_LABEL_KEYS[task.status])}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label={t("projects.taskListColumnPriority")}>
              <span data-testid="task-detail-priority">{task.priority}</span>
            </Descriptions.Item>
            <Descriptions.Item label={t("projects.taskListColumnAssignee")}>
              <span data-testid="task-detail-assignee">
                {task.assignee_type && task.assignee_id
                  ? `${task.assignee_type}:${task.assignee_id}`
                  : DASH}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label={t("projects.taskDetailParent")}>
              <span data-testid="task-detail-parent">
                {parent ? parent.title : task.parent_id || DASH}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label={t("projects.taskListColumnStartAt")}>
              {formatServerDateTime(task.start_at ?? 0, timeZone)}
            </Descriptions.Item>
            <Descriptions.Item label={t("projects.taskListColumnDueAt")}>
              {formatServerDateTime(task.due_at ?? 0, timeZone)}
            </Descriptions.Item>
          </Descriptions>

          <section className={styles.section}>
            <div className={styles.sectionTitle}>
              {t("projects.taskDetailDescription")}
            </div>
            <div
              className={styles.description}
              data-testid="task-detail-description"
            >
              {task.description || DASH}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionTitle}>
              {t("projects.taskDetailDeps")}
            </div>
            <div className={styles.inline} data-testid="task-detail-deps">
              {task.deps?.length ? task.deps.join(", ") : DASH}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionTitle}>
              {t("projects.taskListColumnTags")}
            </div>
            <div className={styles.inline} data-testid="task-detail-tags">
              {task.tags?.length ? (
                <Space size={4} wrap>
                  {task.tags.map((tag) => (
                    <Tag key={tag.tag_id} color={tag.color || undefined}>
                      {tag.name}
                    </Tag>
                  ))}
                </Space>
              ) : (
                DASH
              )}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionTitle}>
              {t("projects.customFieldsTitle")}
            </div>
            <div
              className={styles.inline}
              data-testid="task-detail-custom-fields"
            >
              {task.custom_fields?.length ? (
                <Space direction="vertical" size={2}>
                  {task.custom_fields.map((field) => (
                    <span key={field.field_id}>
                      <span className={styles.fieldLabel}>{field.label}</span>
                      {": "}
                      {String(field.value ?? DASH)}
                    </span>
                  ))}
                </Space>
              ) : (
                DASH
              )}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionTitle}>
              {t("projects.taskDetailAttachments")}
            </div>
            <div
              className={styles.inline}
              data-testid="task-detail-attachments"
            >
              {task.attachments?.length ? (
                <Space direction="vertical" size={4}>
                  {task.attachments.map((attachment) => (
                    <span
                      key={attachment.artifact_id}
                      className={styles.attachment}
                      data-testid={`task-detail-attachment-${attachment.artifact_id}`}
                    >
                      <Paperclip size={12} aria-hidden />
                      <span className={styles.attachmentName}>
                        {attachment.name}
                      </span>
                      <Tooltip title={t("projects.download")}>
                        <button
                          type="button"
                          className={styles.iconButton}
                          data-testid={`task-detail-download-${attachment.artifact_id}`}
                          aria-label={t("projects.download")}
                          onClick={() => void download(attachment)}
                        >
                          <Download size={13} aria-hidden />
                        </button>
                      </Tooltip>
                    </span>
                  ))}
                </Space>
              ) : (
                t("projects.attachmentsEmpty")
              )}
            </div>
          </section>

          {/* ⚠️ 最小只读轨迹（PLAN §4.3）：仅 4 类可得事实，**不是**完整历史。 */}
          <section className={styles.section}>
            <div className={styles.sectionTitle}>
              {t("projects.taskDetailTimeline")}
            </div>
            <ul className={styles.timeline} data-testid="task-detail-timeline">
              <li data-testid="task-detail-timeline-created">
                <span className={styles.timelineNode}>
                  {t("projects.taskDetailTimelineCreated")}
                </span>
                <span className={styles.timelineTime}>
                  {formatServerDateTime(task.created_at, timeZone)}
                </span>
              </li>
              <li data-testid="task-detail-timeline-status">
                <span className={styles.timelineNode}>
                  {t(STATUS_LABEL_KEYS[task.status])}
                </span>
              </li>
              <li data-testid="task-detail-timeline-updated">
                <span className={styles.timelineNode}>
                  {t("projects.taskDetailTimelineUpdated")}
                </span>
                <span className={styles.timelineTime}>
                  {formatServerDateTime(task.updated_at, timeZone)}
                </span>
              </li>
              {task.thread_id ? (
                <li data-testid="task-detail-timeline-dispatched">
                  <span className={styles.timelineNode}>
                    {t("projects.taskDetailTimelineDispatched")}
                  </span>
                </li>
              ) : null}
            </ul>
          </section>

          <TaskCreateModal
            open={editing}
            projectId={projectId}
            tasks={tasks}
            canEdit={canEdit}
            mode="edit"
            initialValues={taskToValues(task)}
            onSubmitEdit={submitEdit}
            onClose={() => setEditing(false)}
            onCreated={onChanged}
          />
        </>
      )}
    </div>
  );
}
