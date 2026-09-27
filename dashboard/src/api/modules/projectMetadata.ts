import { request, requestBlob, requestUpload } from "../request";
import type { UploadProgressHandler } from "../request";
import type {
  ProjectAttachment,
  ProjectCustomFieldDefinition,
  ProjectCustomFieldType,
  ProjectCustomFieldWriteValue,
  ProjectTag,
  ProjectTagDefinition,
  ProjectTaskCustomFields,
} from "./projects";

/**
 * Typed wrappers for the project metadata surface: tags (PLAN §4),
 * custom fields (PLAN §6.3) and attachments (PLAN §7.4 / §7.5).
 *
 * Types live in ``./projects`` — the single front-end type landing point for
 * this round; this module only adds the request shapes and paths.
 */

function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
}

function tagPath(projectId: string, tagId: string): string {
  return `${projectPath(projectId)}/tags/${encodeURIComponent(tagId)}`;
}

function fieldPath(projectId: string, fieldId: string): string {
  return `${projectPath(projectId)}/custom-fields/${encodeURIComponent(
    fieldId,
  )}`;
}

function attachmentPath(projectId: string, artifactId: string): string {
  return `${projectPath(projectId)}/attachments/${encodeURIComponent(
    artifactId,
  )}`;
}

function taskPath(projectId: string, taskId: string): string {
  return `${projectPath(projectId)}/tasks/${encodeURIComponent(taskId)}`;
}

export interface ProjectTagCreateBody {
  name: string;
  /** ``''`` or ``#RRGGBB``. */
  color?: string;
}

export interface ProjectTagUpdateBody {
  name?: string;
  color?: string;
}

export interface ProjectCustomFieldCreateBody {
  key: string;
  label: string;
  type: ProjectCustomFieldType;
  required?: boolean;
  /** Required (and non-empty) only for ``type: "select"``. */
  options?: string[];
  sort_order?: number;
}

export interface ProjectCustomFieldUpdateBody {
  label?: string;
  required?: boolean;
  options?: string[];
  sort_order?: number;
}

/** ``{"deleted": bool}`` envelope used by the project-domain delete routes. */
export interface MetadataDeleteResult {
  deleted: boolean;
}

export const projectMetadataApi = {
  // ---------- tags (PLAN §4) ----------

  listTags: (projectId: string) =>
    request<ProjectTagDefinition[]>(`${projectPath(projectId)}/tags`),

  createTag: (projectId: string, body: ProjectTagCreateBody) =>
    request<ProjectTagDefinition>(`${projectPath(projectId)}/tags`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTag: (projectId: string, tagId: string, body: ProjectTagUpdateBody) =>
    request<ProjectTagDefinition>(tagPath(projectId, tagId), {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteTag: (projectId: string, tagId: string) =>
    request<MetadataDeleteResult>(tagPath(projectId, tagId), {
      method: "DELETE",
    }),

  /** Full replacement of one task's tags; returns the resolved set. */
  setTaskTags: (projectId: string, taskId: string, tagIds: string[]) =>
    request<ProjectTag[]>(`${taskPath(projectId, taskId)}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tags: tagIds }),
    }),

  // ---------- custom fields (PLAN §6.3) ----------

  listCustomFields: (projectId: string) =>
    request<ProjectCustomFieldDefinition[]>(
      `${projectPath(projectId)}/custom-fields`,
    ),

  createCustomField: (projectId: string, body: ProjectCustomFieldCreateBody) =>
    request<ProjectCustomFieldDefinition>(
      `${projectPath(projectId)}/custom-fields`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  updateCustomField: (
    projectId: string,
    fieldId: string,
    body: ProjectCustomFieldUpdateBody,
  ) =>
    request<ProjectCustomFieldDefinition>(fieldPath(projectId, fieldId), {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteCustomField: (projectId: string, fieldId: string) =>
    request<MetadataDeleteResult>(fieldPath(projectId, fieldId), {
      method: "DELETE",
    }),

  /** Read ring: definitions plus this task's values, keyed by ``field_id``. */
  getTaskCustomFields: (projectId: string, taskId: string) =>
    request<ProjectTaskCustomFields>(
      `${taskPath(projectId, taskId)}/custom-fields`,
    ),

  /**
   * Write ring: full replacement. The server always validates every
   * ``required`` definition, so pass the complete value map.
   */
  setTaskCustomFields: (
    projectId: string,
    taskId: string,
    values: Record<string, ProjectCustomFieldWriteValue>,
  ) =>
    request<ProjectTaskCustomFields>(
      `${taskPath(projectId, taskId)}/custom-fields`,
      { method: "PUT", body: JSON.stringify({ values }) },
    ),

  // ---------- attachments (PLAN §7.4 / §7.5) ----------

  /**
   * Stage an attachment **before** the task exists (``task_id: null``).
   * This is what the create-task dialog's 📎 uses (FIND-1).
   */
  uploadPendingAttachment: (
    projectId: string,
    file: File,
    onProgress?: UploadProgressHandler,
  ) => {
    const form = new FormData();
    form.append("file", file);
    return requestUpload<ProjectAttachment>(
      `${projectPath(projectId)}/attachments`,
      form,
      {},
      onProgress,
    );
  },

  /** Upload straight onto an existing task. */
  uploadTaskAttachment: (
    projectId: string,
    taskId: string,
    file: File,
    onProgress?: UploadProgressHandler,
  ) => {
    const form = new FormData();
    form.append("file", file);
    return requestUpload<ProjectAttachment>(
      `${taskPath(projectId, taskId)}/attachments`,
      form,
      {},
      onProgress,
    );
  },

  /** Bind a pending attachment to a task (already-bound rows are rejected). */
  bindAttachment: (projectId: string, artifactId: string, taskId: string) =>
    request<ProjectAttachment>(attachmentPath(projectId, artifactId), {
      method: "PATCH",
      body: JSON.stringify({ task_id: taskId }),
    }),

  listTaskAttachments: (projectId: string, taskId: string) =>
    request<ProjectAttachment[]>(`${taskPath(projectId, taskId)}/attachments`),

  /**
   * Download by id (the stored path is never exposed). Pending rows are
   * downloadable too, so a just-staged file can be previewed.
   */
  downloadAttachment: (projectId: string, artifactId: string) =>
    requestBlob(`${attachmentPath(projectId, artifactId)}/download`),

  deleteAttachment: (projectId: string, artifactId: string) =>
    request<MetadataDeleteResult>(attachmentPath(projectId, artifactId), {
      method: "DELETE",
    }),
};
