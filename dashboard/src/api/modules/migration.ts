import { requestUpload } from "../request";

export interface MigrationImportResult {
  ok: boolean;
  agent_id: string;
  agent_created: boolean;
  workspace_files_written: number;
  workspace_files_skipped: number;
  /** Core identity files written (SOUL.md, USER.md, AGENTS.md, etc.) */
  identity_files_written: string[];
  /** Number of enabled skill directories imported */
  skills_imported: number;
  uploads_written: number;
  uploads_skipped: number;
  cron_jobs_imported: number;
  cron_jobs_skipped: number;
  sessions_imported: number;
  sessions_skipped: number;
  warnings: string[];
  errors: string[];
}

export const migrationApi = {
  /**
   * Import a LightClaw migration ZIP into Octop.
   * Creates a new agent with workspace, sessions, uploads, and cron jobs.
   */
  importLightclaw: (
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<MigrationImportResult> => {
    const formData = new FormData();
    formData.append("file", file);
    return requestUpload<MigrationImportResult>(
      "/admin/migration/import-lightclaw",
      formData,
      {},
      onProgress,
    );
  },
};
