import { request } from "../request";

export type ProjectStatus = "draft" | "active" | "paused" | "archived";

export type ProjectSubjectType = "user" | "agent" | "team";

export type ProjectMemberRole = "owner" | "admin" | "member" | "viewer";

export type ProjectTaskStatus =
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
  start_at?: number | null;
  due_at?: number | null;
}

export interface ProjectUpdateBody {
  name?: string;
  goal?: string;
  status?: ProjectStatus;
  start_at?: number | null;
  due_at?: number | null;
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

  /** Oldest first, i.e. a replay of what happened in the project. */
  timeline: (projectId: string, limit?: number) =>
    request<ProjectTimelineEvent[]>(
      limit
        ? `${projectPath(projectId)}/timeline?limit=${limit}`
        : `${projectPath(projectId)}/timeline`,
    ),
};
