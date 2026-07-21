import { request, requestBlob, requestUpload } from "../request";

export interface BackupFileItem {
  name: string;
  size: number;
  modified_at: string;
  created_at: string;
}

export interface BackupListResponse {
  dir: string;
  items: BackupFileItem[];
}

export const backupApi = {
  listBackups: () => request<BackupListResponse>("/admin/backup/list"),

  createBackup: () =>
    request<{ ok: boolean; item: BackupFileItem }>("/admin/backup/create", {
      method: "POST",
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
};
