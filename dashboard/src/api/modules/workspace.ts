import { request, requestBlob, requestUpload, getAuthToken } from "../request";
import { getApiUrl } from "../config";
import { withFromWorkspace } from "../../utils/fromWorkspace";
import type {
  MdFileInfo,
  MdFileContent,
  DailyMemoryFile,
  FileTreeNode,
  WorkspaceFileContent,
  SyncFromOpenClawRequest,
  SyncFromOpenClawResponse,
} from "../types";

export const workspaceApi = {
  getWorkspaceTree: () => request<FileTreeNode[]>("/workspace/tree"),

  getTreeChildren: (path: string) =>
    request<FileTreeNode[]>(
      `/workspace/tree-children?path=${encodeURIComponent(path)}`,
    ),

  readFileContent: (path: string) =>
    request<WorkspaceFileContent>(
      `/workspace/file?path=${encodeURIComponent(path)}`,
    ),

  /** Fetch image with auth header and return an object URL (caller must revoke when done). */
  readImageAsObjectUrl: async (path: string): Promise<string> => {
    const blob = await requestBlob(
      `/workspace/media?path=${encodeURIComponent(path)}`,
    );
    return URL.createObjectURL(blob);
  },

  /**
   * Build a direct streaming URL for video/audio files.
   * Uses ?token= query param so the browser can make Range requests
   * (seek/scrub) without needing an Authorization header.
   */
  getMediaStreamUrl: (path: string): string => {
    const base = getApiUrl(`/workspace/media?path=${encodeURIComponent(path)}`);
    const token = getAuthToken();
    return token ? `${base}&token=${encodeURIComponent(token)}` : base;
  },

  listFiles: () =>
    request<MdFileInfo[]>("/agent/files").then((files) =>
      files.map((file) => ({
        ...file,
        updated_at: new Date(file.modified_time).getTime(),
      })),
    ),

  loadFile: (fileName: string) =>
    request<MdFileContent>(`/agent/files/${encodeURIComponent(fileName)}`),

  saveFile: (fileName: string, content: string) =>
    request<Record<string, unknown>>(
      `/agent/files/${encodeURIComponent(fileName)}`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),

  // Save workspace file content (any editable file in workspace)
  saveWorkspaceFile: (filePath: string, content: string) =>
    request<Record<string, unknown>>(`/workspace/file`, {
      method: "PUT",
      body: JSON.stringify({ path: filePath, content }),
    }),

  // Workspace package download (full zip archive)
  downloadWorkspaceArchive: (agentId: string): Promise<Blob> =>
    requestBlob(`/agents/${agentId}/workspace/archive`),

  importWorkspaceArchive: (
    agentId: string,
    file: File,
    mode: "merge" | "replace",
  ): Promise<{ ok: boolean; imported: number; warnings?: string[] }> => {
    const formData = new FormData();
    formData.append("file", file);
    return requestUpload(
      `/agents/${agentId}/workspace/archive?mode=${mode}`,
      formData,
    );
  },

  deleteWorkspaceFile: (agentId: string, path: string): Promise<void> =>
    request<void>(
      withFromWorkspace(
        `/agents/${agentId}/workspace/file?path=${encodeURIComponent(path)}`,
      ),
      { method: "DELETE" },
    ),

  moveWorkspaceFile: (
    agentId: string,
    path: string,
    destination: string,
  ): Promise<{ path: string }> =>
    request<{ path: string }>(
      withFromWorkspace(
        `/agents/${agentId}/workspace/move?path=${encodeURIComponent(path)}`,
      ),
      {
        method: "POST",
        body: JSON.stringify({ destination }),
      },
    ),

  mkdirWorkspaceDir: (
    agentId: string,
    path: string,
  ): Promise<{ path: string; is_dir: boolean }> =>
    request<{ path: string; is_dir: boolean }>(
      withFromWorkspace(
        `/agents/${agentId}/workspace/mkdir?path=${encodeURIComponent(path)}`,
      ),
      { method: "POST" },
    ),

  createWorkspaceFile: (
    agentId: string,
    path: string,
    content = "",
  ): Promise<{ path: string; size: number }> =>
    request<{ path: string; size: number }>(
      withFromWorkspace(
        `/agents/${agentId}/workspace/file?path=${encodeURIComponent(path)}`,
      ),
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),

  // Workspace package download (legacy single-path)
  downloadWorkspace: (): Promise<Blob> => requestBlob("/workspace/download"),

  // Single file download
  downloadFile: (path: string): Promise<Blob> =>
    requestBlob(`/workspace/download-file?path=${encodeURIComponent(path)}`),

  // Delete a file or directory
  deleteFile: (path: string): Promise<{ deleted: boolean; path: string }> =>
    request<{ deleted: boolean; path: string }>(
      `/workspace/file?path=${encodeURIComponent(path)}`,
      {
        method: "DELETE",
      },
    ),

  // File upload functionality
  uploadFile: (file: File): Promise<{ success: boolean; message: string }> => {
    const formData = new FormData();
    formData.append("file", file);
    return requestUpload<{ success: boolean; message: string }>(
      "/workspace/upload",
      formData,
    );
  },

  // Sync from OpenClaw
  syncFromOpenClaw: (syncRequest?: SyncFromOpenClawRequest) =>
    request<SyncFromOpenClawResponse>(`/workspace/sync-from-openclaw`, {
      method: "POST",
      body: JSON.stringify(syncRequest || {}),
    }),

  /** Initialize workspace with default prompt files and skills.
   *  Equivalent to `octop init` — safe to call repeatedly. */
  initializeWorkspace: () =>
    request<{ ok: boolean }>("/workspace/initialize", { method: "POST" }),

  listDailyMemory: () =>
    request<MdFileInfo[]>("/agent/memory").then((files) =>
      files.map((file) => {
        const date = file.filename.replace(".md", "");
        return {
          ...file,
          date,
          updated_at: new Date(file.modified_time).getTime(),
        } as DailyMemoryFile;
      }),
    ),

  loadDailyMemory: (date: string) =>
    request<MdFileContent>(`/agent/memory/${encodeURIComponent(date)}.md`),

  saveDailyMemory: (date: string, content: string) =>
    request<Record<string, unknown>>(
      `/agent/memory/${encodeURIComponent(date)}.md`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),

  deleteDailyMemory: (filename: string) =>
    request<{ deleted: boolean; filename: string }>(
      `/agent/memory/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    ),

  forgetMemory: (params: { query?: string; chunk_ids?: string[] }) =>
    request<{
      success: boolean;
      message: string;
      deleted_count: number;
    }>("/agent/memory/forget", {
      method: "POST",
      body: JSON.stringify(params),
    }),
};
