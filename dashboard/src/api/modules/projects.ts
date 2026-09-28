import { request, requestUpload } from "../request";

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
  /** 稳定标识（如 `user:1`）—— ★ **不要拿它显示**；显示用 `actor_name`。 */
  actor: string;
  /** 操作人显示名（后端 join；`null`/缺失 ⇒ UI **回退** `actor`，不得空白）。 */
  actor_name?: string | null;
  action: string;
  task_id: string | null;
  payload: Record<string, unknown>;
  at: number;
}

/** 项目/任务讨论线的一条留言（逐字对照后端 `CommentOut`）。 */
export interface ProjectComment {
  comment_id: string;
  project_id: string;
  /** null = 项目级留言（挂在任务上时非空）。 */
  task_id: string | null;
  thread_id: string | null;
  /** ``user | agent``（后端判定，不由前端选择 —— `CommentCreate` 无该字段）。 */
  author_type: string;
  author_id: string;
  /** 作者显示名（后端 join；解析不到为 `null` ⇒ UI **回退** `author_type:author_id`，不得空白）。 */
  name?: string | null;
  body: string;
  source: string;
  /** ``none | conclusion``。 */
  node_type: string;
  concluded: boolean;
  /** 采纳者（本批只写 `user`）；未采纳时三者均为 null。 */
  concluded_by_type?: string | null;
  concluded_by_id?: string | null;
  /** ★ 采纳者显示名由**后端**按既有解析面解析好 ⇒ 前端**直接用**，不自己拼 `type:id`。 */
  concluded_by_name?: string | null;
  created_at: number;
  updated_at: number;
}

/** `POST /projects/{pid}/comments` 请求体（逐字对照后端 `CommentCreate`）。 */
export interface ProjectCommentCreateBody {
  /** 空白由后端 422 拒绝（前端只做按钮禁用）。 */
  body: string;
  task_id?: string | null;
  /**
   * ★ 被提及者（`[{type, id}]`）—— **只由显式 UI 动作产生**（**不做文本解析**）。
   * ★ 服务端**只存不解析**；★ 省略 = NULL 与 `[]`（显式"没 @ 任何人"）是**两种事实**，不得塌缩。
   */
  mentions?: Array<{ type: string; id: string }> | null;
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

  /**
   * Oldest first, i.e. a replay of what happened in the project.
   *
   * 批次八：**只增** `taskId`（后端 `GET …/timeline` 已支持 `task_id` 过滤）与
   * `limit`。★ 此前该函数**无任何调用点**（已核实），故改为可选对象不会破坏既有行为；
   * 默认（不传）时请求 URL 与改动前**逐字相同** ✓。
   */
  timeline: (
    projectId: string,
    params?: { limit?: number; taskId?: string },
  ) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.taskId) query.set("task_id", params.taskId);
    const qs = query.toString();
    return request<ProjectTimelineEvent[]>(
      `${projectPath(projectId)}/timeline${qs ? `?${qs}` : ""}`,
    );
  },

  // ---------- discussion / comments（批次八：逐字对照后端 4 条路由） ----------

  /** `GET …/comments`（可选 `task_id` / `concluded` 过滤）。 */
  listComments: (
    projectId: string,
    params?: {
      taskId?: string;
      concluded?: boolean;
      /** ★ 与 `authorType` **成对**（只给 id ⇒ 服务端 400）。 */
      authorId?: string;
      /** `user | agent` —— 与 `authorId` 成对。 */
      authorType?: string;
      /** ★ 冻结枚举值只有 `"me"`（= **关于调用者自己**；服务端 `Literal` ⇒ 非法值 422）。 */
      relevance?: "me";
    },
  ) => {
    const query = new URLSearchParams();
    if (params?.taskId) query.set("task_id", params.taskId);
    if (params?.concluded !== undefined)
      query.set("concluded", String(params.concluded));
    if (params?.authorId) query.set("author_id", params.authorId);
    if (params?.authorType) query.set("author_type", params.authorType);
    if (params?.relevance) query.set("relevance", params.relevance);
    const qs = query.toString();
    return request<ProjectComment[]>(
      `${projectPath(projectId)}/comments${qs ? `?${qs}` : ""}`,
    );
  },

  /** `POST …/comments`（201；空白 → 422，前端只禁用按钮）。 */
  createComment: (projectId: string, body: ProjectCommentCreateBody) =>
    request<ProjectComment>(`${projectPath(projectId)}/comments`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** `POST …/comments/{cid}/conclude`（幂等；标记为结论）。 */
  concludeComment: (projectId: string, commentId: string) =>
    request<ProjectComment>(
      `${projectPath(projectId)}/comments/${encodeURIComponent(
        commentId,
      )}/conclude`,
      { method: "POST" },
    ),

  /** `PATCH …/comments/{cid}` —— 编辑留言正文（返回更新后的 `CommentOut`）。 */
  updateComment: (projectId: string, commentId: string, body: string) =>
    request<ProjectComment>(
      `${projectPath(projectId)}/comments/${encodeURIComponent(commentId)}`,
      { method: "PATCH", body: JSON.stringify({ body }) },
    ),

  /**
   * `DELETE …/comments/{cid}` —— **硬删**（返回 `{ deleted: boolean }`）。
   * ★ 若该留言已采纳为结论，服务端 **409** `PROJECT_COMMENT_CONCLUDED`（前端**事前禁用**入口，见 `DynamicTab`）。
   */
  deleteComment: (projectId: string, commentId: string) =>
    request<{ deleted: boolean }>(
      `${projectPath(projectId)}/comments/${encodeURIComponent(commentId)}`,
      { method: "DELETE" },
    ),

  /** `POST …/attachments` —— 暂存（staged）一个附件，随后用 `bindAttachment` 挂到留言/任务。 */
  uploadStagedAttachment: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestUpload<ProjectAttachment>(
      `${projectPath(projectId)}/attachments`,
      form,
    );
  },

  /**
   * `PATCH …/attachments/{artifactId}` —— 绑定暂存附件。
   * ★ 服务端要求 `task_id` / `comment_id` **恰好一个**（都传或都不传 ⇒ 400；已绑 ⇒ 409）。
   */
  bindAttachment: (
    projectId: string,
    artifactId: string,
    target: { taskId?: string; commentId?: string },
  ) =>
    request<ProjectAttachment>(
      `${projectPath(projectId)}/attachments/${encodeURIComponent(artifactId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          ...(target.taskId ? { task_id: target.taskId } : {}),
          ...(target.commentId ? { comment_id: target.commentId } : {}),
        }),
      },
    ),

  /**
   * `DELETE …/comments/{cid}/conclude`（幂等；取消结论标记）。
   * ★ 与 PLAN 措辞的差异：**不是** POST —— 以真实路由为准（`projects.py:767` 是 `@router.delete`）。
   */
  unconcludeComment: (projectId: string, commentId: string) =>
    request<ProjectComment>(
      `${projectPath(projectId)}/comments/${encodeURIComponent(
        commentId,
      )}/conclude`,
      { method: "DELETE" },
    ),
};
