import { request } from "../request";

export type ProjectStatus =
  | "draft"
  | "active"
  | "paused"
  | "completed"
  | "cancelled"
  | "archived";

export type ProjectSubjectType = "user" | "agent" | "team";

export type ProjectMemberRole = "owner" | "admin" | "member" | "viewer";

/**
 * Task statuses, v2 (PLAN §1.1): ``planning`` is prepended, the relative order
 * of the existing six values is preserved verbatim.
 */
export type ProjectTaskStatus =
  | "planning"
  | "todo"
  | "doing"
  | "review"
  | "done"
  | "blocked"
  | "cancelled";

export interface ProjectOut {
  project_id: string;
  name: string;
  goal: string;
  status: ProjectStatus;
  owner_user_id: number;
  memory_namespace: string;
  kb_id: string | null;
  start_at: number | null;
  due_at: number | null;
  created_at: number;
  updated_at: number;
}

export interface ProjectMember {
  subject_type: ProjectSubjectType;
  subject_id: string;
  user_id: number | null;
  role: ProjectMemberRole;
  created_at: number;
  /**
   * 主体显示名（后端 `MemberOut.name`，批次六新增）：agent → `agents.name` ·
   * user → `users.display_name`（`username` 兜底）· team → 团队名。
   * **可空/可缺省** —— 解析不到时为 `null`，UI 回退显示 `subject_id`（不得空白）。
   */
  name?: string | null;
}

/** Tag as resolved on a task (PLAN §4: ``TaskOut.tags``). */
export interface ProjectTag {
  tag_id: string;
  name: string;
  color: string;
}

/** Tag definition row (`GET /api/projects/{pid}/tags`). */
export interface ProjectTagDefinition extends ProjectTag {
  created_at: number;
}

/** Custom-field type system (PLAN §6.2: exactly four kinds). */
export type ProjectCustomFieldType = "text" | "number" | "date" | "select";

/** Field definition (`GET /api/projects/{pid}/custom-fields`). */
export interface ProjectCustomFieldDefinition {
  field_id: string;
  key: string;
  label: string;
  type: ProjectCustomFieldType;
  required: boolean;
  options: string[];
  sort_order: number;
  created_at: number;
  updated_at: number;
}

/** Value accepted by the write endpoints (PLAN §6.2). */
export type ProjectCustomFieldWriteValue = string | number | null;

/** Resolved value on a task (`TaskOut.custom_fields`). */
export interface ProjectCustomFieldValue {
  field_id: string;
  key: string;
  label: string;
  type: ProjectCustomFieldType;
  value: ProjectCustomFieldWriteValue;
}

/**
 * Attachment row (PLAN §7.4) — never carries the stored path.
 * ``task_id === null`` means the row is staged (pending) and not yet bound
 * to a task (PLAN §7.5).
 */
export interface ProjectAttachment {
  artifact_id: string;
  name: string;
  size: number;
  mime: string;
  created_at: number;
  uploader: string;
  task_id: string | null;
}

/** Task-level custom-field read shape (`GET .../tasks/{tid}/custom-fields`). */
export interface ProjectTaskCustomFields {
  definitions: ProjectCustomFieldDefinition[];
  values: Record<string, ProjectCustomFieldWriteValue>;
}

export interface ProjectTask {
  task_id: string;
  project_id: string;
  parent_id: string | null;
  title: string;
  description: string;
  status: ProjectTaskStatus;
  assignee_type: string | null;
  assignee_id: string | null;
  priority: number;
  deps: string[];
  thread_id: string | null;
  origin_node_id: string | null;
  due_at: number | null;
  /** Start date, Unix seconds (PLAN §5). */
  start_at: number | null;
  /** Resolved tags, oldest first (PLAN §4). */
  tags: ProjectTag[];
  /** Resolved custom-field values (PLAN §6.3 read ring). */
  custom_fields: ProjectCustomFieldValue[];
  /** Attachments already bound to this task (PLAN §7.4). */
  attachments: ProjectAttachment[];
  sort_order: number;
  created_by: number;
  created_at: number;
  updated_at: number;
}

export interface ProjectTimelineEvent {
  actor: string;
  action: string;
  task_id: string | null;
  payload: Record<string, unknown>;
  at: number;
}

export interface ProjectCreateBody {
  name: string;
  goal?: string;
  /** Initial status (all six are selectable); omitted → the server's `draft`. */
  status?: ProjectStatus | null;
  start_at?: number | null;
  due_at?: number | null;
}

export interface ProjectUpdateBody {
  name?: string;
  goal?: string;
  status?: ProjectStatus;
  start_at?: number | null;
  due_at?: number | null;
  /**
   * Knowledge-base rebind — three states, decided by whether the key is present
   * (PLAN §4.1): absent = leave it, `null` = unbind, a value = rebind.
   *
   * ★ Presence is what raises the **whole request** to `PROJECT_MANAGE_CONFIG`
   * (PLAN §4.3), so a goal-only edit must omit the key.
   */
  kb_id?: string | null;
  /** Explicitly store `null` in `start_at` / `due_at`. */
  clear_start_at?: boolean;
  clear_due_at?: boolean;
}

export interface ProjectMemberBody {
  subject_type?: ProjectSubjectType;
  subject_id: string;
  role?: ProjectMemberRole;
}

export interface ProjectTaskCreateBody {
  title: string;
  description?: string;
  parent_id?: string | null;
  assignee_type?: string | null;
  assignee_id?: string | null;
  priority?: number;
  deps?: string[];
  due_at?: number | null;
  /** Target column; omitted/``null`` → server lands ``planning`` (PLAN §2.1). */
  status?: ProjectTaskStatus | null;
  /** Start date, Unix seconds. */
  start_at?: number | null;
  /** Tag ids (full replacement). */
  tags?: string[];
  /**
   * ``field_id → value``. ``null`` skips required-field validation,
   * ``{}`` explicitly clears and validates (PLAN §6.3).
   */
  custom_fields?: Record<string, ProjectCustomFieldWriteValue> | null;
  /** Staged (pending) attachment ids bound after the task row is created. */
  attachment_ids?: string[];
}

export interface ProjectTaskUpdateBody {
  title?: string;
  description?: string;
  parent_id?: string | null;
  assignee_type?: string | null;
  assignee_id?: string | null;
  priority?: number;
  deps?: string[];
  due_at?: number | null;
  /** Routed through the task state machine by the backend. */
  status?: ProjectTaskStatus;
  start_at?: number | null;
  /** Tag ids (full replacement). */
  tags?: string[];
  custom_fields?: Record<string, ProjectCustomFieldWriteValue> | null;
}

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

export const projectsApi = {
  /** Projects the caller is a member of (the API never lists anything else). */
  list: () => request<ProjectOut[]>("/projects"),

  create: (body: ProjectCreateBody) =>
    request<ProjectOut>("/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  get: (projectId: string) => request<ProjectOut>(projectPath(projectId)),

  update: (projectId: string, body: ProjectUpdateBody) =>
    request<ProjectOut>(projectPath(projectId), {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  /** DELETE archives the project (read-only, keeps members/tasks/KB). */
  archive: (projectId: string) =>
    request<ProjectOut>(projectPath(projectId), { method: "DELETE" }),

  listMembers: (projectId: string) =>
    request<ProjectMember[]>(`${projectPath(projectId)}/members`),

  /** Idempotent per subject: re-adding an existing subject changes its role. */
  addMember: (projectId: string, body: ProjectMemberBody) =>
    request<ProjectMember>(`${projectPath(projectId)}/members`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  removeMember: (
    projectId: string,
    subjectType: ProjectSubjectType,
    subjectId: string,
  ) =>
    request<{ removed: boolean }>(
      `${projectPath(projectId)}/members/${subjectType}/${encodeURIComponent(
        subjectId,
      )}`,
      { method: "DELETE" },
    ),

  listTasks: (projectId: string, status?: ProjectTaskStatus) =>
    request<ProjectTask[]>(
      status
        ? `${projectPath(projectId)}/tasks?status=${encodeURIComponent(status)}`
        : `${projectPath(projectId)}/tasks`,
    ),

  createTask: (projectId: string, body: ProjectTaskCreateBody) =>
    request<ProjectTask>(`${projectPath(projectId)}/tasks`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTask: (
    projectId: string,
    taskId: string,
    body: ProjectTaskUpdateBody,
  ) =>
    request<ProjectTask>(
      `${projectPath(projectId)}/tasks/${encodeURIComponent(taskId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  deleteTask: (projectId: string, taskId: string) =>
    request<{ deleted: boolean }>(
      `${projectPath(projectId)}/tasks/${encodeURIComponent(taskId)}`,
      { method: "DELETE" },
    ),

  /**
   * Dispatch a task to its ``agent`` / ``team`` assignee — reuses the existing
   * backend route (PLAN §8.2). Assignees of type ``user`` are rejected 409
   * ``PROJECT_TASK_DISPATCH_INVALID``, so callers must gate on the assignee
   * type before calling.
   */
  dispatchTask: (projectId: string, taskId: string) =>
    request<ProjectTask>(
      `${projectPath(projectId)}/tasks/${encodeURIComponent(taskId)}:dispatch`,
      { method: "POST" },
    ),

  /** Oldest first, i.e. a replay of what happened in the project. */
  timeline: (projectId: string, limit?: number) =>
    request<ProjectTimelineEvent[]>(
      limit
        ? `${projectPath(projectId)}/timeline?limit=${limit}`
        : `${projectPath(projectId)}/timeline`,
    ),
};
