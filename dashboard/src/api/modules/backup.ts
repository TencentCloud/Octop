import { request, requestBlob, requestUpload } from "../request";

export type RemoteMirrorStatus =
  | "remote_ok"
  | "unverified"
  | "remote_failed"
  | null;

export interface BackupFileItem {
  name: string;
  size: number;
  modified_at: string;
  created_at: string;
  includes_config?: boolean;
  includes_workspaces?: boolean;
  includes_skill_packages?: boolean;
  includes_plugins?: boolean;
  includes_knowledge?: boolean;
  includes_chats?: boolean;
  remote_status?: RemoteMirrorStatus;
  remote_checked_at?: string;
  remote_detail?: string;
}

export interface BackupListResponse {
  dir: string;
  items: BackupFileItem[];
}

export interface RemoteMirrorSummary {
  name: string;
  status: Exclude<RemoteMirrorStatus, null>;
  checked_at: string;
  detail?: string;
  sha256?: string | null;
}

export interface RemoteBackupSummary {
  remote_enabled: boolean;
  remote_backend_id: number | null;
  kind?: string | null;
  endpoint?: string | null;
  base_dir?: string | null;
  backend_name?: string | null;
  backend_enabled?: boolean;
  last_mirror?: RemoteMirrorSummary | null;
  detail?: string;
}

export interface AutoBackupSettings {
  auto_enabled: boolean;
  schedule: string;
  retention_count: number;
  include_config: boolean;
  include_workspaces: boolean;
  include_skill_packages: boolean;
  include_plugins: boolean;
  include_knowledge: boolean;
  include_chats: boolean;
  remote_enabled?: boolean;
  remote_backend_id?: number | null;
  remote?: RemoteBackupSummary;
  scheduled?: boolean;
}

export interface CreateBackupOptions {
  include_config: boolean;
  include_workspaces: boolean;
  include_skill_packages: boolean;
  include_plugins: boolean;
  include_knowledge: boolean;
  include_chats: boolean;
}

export type BackupOperationKind = "create" | "restore" | "auto" | "export";

export interface BackupStatusResponse {
  busy: boolean;
  operation: BackupOperationKind | null;
}

export interface RemoteWebDavConfig {
  url: string;
  username?: string;
  password?: string | null;
  base_dir?: string;
  verify_ssl?: boolean;
  allow_insecure?: boolean;
}

export interface RemoteBackupObject {
  name: string;
  size: number;
  modified_at: string | null;
  remote_status?: RemoteMirrorStatus;
  remote_checked_at?: string;
}

export const backupApi = {
  listBackups: () => request<BackupListResponse>("/admin/backup/list"),

  getStatus: () => request<BackupStatusResponse>("/admin/backup/status"),

  getAutoSettings: () => request<AutoBackupSettings>("/admin/backup/auto"),

  updateAutoSettings: (body: {
    auto_enabled: boolean;
    schedule: string;
    retention_count: number;
    include_config: boolean;
    include_workspaces: boolean;
    include_skill_packages: boolean;
    include_plugins: boolean;
    include_knowledge: boolean;
    include_chats: boolean;
    remote_enabled?: boolean;
    remote_backend_id?: number | null;
  }) =>
    request<{ ok: boolean } & AutoBackupSettings>("/admin/backup/auto", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  runAutoBackup: () =>
    request<{ ok: boolean; item: BackupFileItem }>("/admin/backup/auto/run", {
      method: "POST",
    }),

  createBackup: (options: CreateBackupOptions) =>
    request<{ ok: boolean; item: BackupFileItem }>("/admin/backup/create", {
      method: "POST",
      body: JSON.stringify(options),
    }),

  downloadBackup: (filename: string): Promise<Blob> =>
    requestBlob(`/admin/backup/files/${encodeURIComponent(filename)}`),

  restoreBackup: (
    filename: string,
    restoreConfig = true,
  ): Promise<{
    ok: boolean;
    name: string;
    agents: number;
    workspace_files: number;
  }> => {
    const qs = restoreConfig ? "" : "?restore_config=false";
    return request(
      `/admin/backup/files/${encodeURIComponent(filename)}/restore${qs}`,
      {
        method: "POST",
      },
    );
  },

  deleteBackup: (filename: string) =>
    request<void>(`/admin/backup/files/${encodeURIComponent(filename)}`, {
      method: "DELETE",
    }),

  /** Upload archive into backups dir (does not restore). */
  uploadBackup: (
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<{ ok: boolean; item: BackupFileItem }> => {
    const formData = new FormData();
    formData.append("file", file);
    return requestUpload("/admin/backup/import", formData, {}, onProgress);
  },

  /** Ephemeral download without saving to backups dir. */
  exportBackup: (): Promise<Blob> => requestBlob("/admin/backup/export"),

  saveRemoteWebDav: (body: RemoteWebDavConfig) =>
    request<{ ok: boolean } & AutoBackupSettings>("/admin/backup/remote", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  testRemote: (body?: RemoteWebDavConfig | null) =>
    request<{ ok: boolean }>("/admin/backup/remote/test", {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  listRemote: () =>
    request<{ items: RemoteBackupObject[] }>("/admin/backup/remote/list"),

  pullRemote: (filename: string) =>
    request<{ ok: boolean; item: BackupFileItem }>("/admin/backup/remote/pull", {
      method: "POST",
      body: JSON.stringify({ filename }),
    }),

  mirrorRemote: (filename: string) =>
    request<{
      ok: boolean;
      name: string;
      remote_status: Exclude<RemoteMirrorStatus, null>;
      remote_reason?: string;
    }>("/admin/backup/remote/mirror", {
      method: "POST",
      body: JSON.stringify({ filename }),
    }),
};
