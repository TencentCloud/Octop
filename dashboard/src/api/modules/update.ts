import { request } from "../request";

export interface UpdateStatus {
  current_version: string;
  latest_version: string | null;
  has_update: boolean;
  is_editable: boolean;
  /** Non-null when the process was launched via `octop service start` (systemd or launchd). */
  service_mode: "systemd" | "launchd" | null;
  /** True when Octop is spawned by the Wails desktop shell (or ``OCTOP_DESKTOP=1``). */
  desktop?: boolean;
  error: string | null;
  last_check_time: string | null;
  /** Markdown changelog for latest_version, null if not available. */
  release_notes: string | null;
}

export interface UpgradeStarted {
  task_id: string;
  status: "started";
}

export interface UpgradeProgress {
  task_id: string;
  status: "running" | "complete" | "error";
  stage: string | null;
  percent: number | null;
  new_version: string | null;
  success: boolean | null;
  error: string | null;
  mirror_errors: string[] | null;
}

export interface RestartResponse {
  status: "restarting";
  service_mode: string;
}

export const updateApi = {
  getUpdateStatus: () => request<UpdateStatus>("/update/status"),
  checkForUpdates: () =>
    request<UpdateStatus>("/update/check", { method: "POST" }),
  triggerUpgrade: () =>
    request<UpgradeStarted>("/update/upgrade", { method: "POST" }),
  getUpgradeProgress: (taskId: string) =>
    request<UpgradeProgress>(
      `/update/progress?task_id=${encodeURIComponent(taskId)}`,
    ),
  restartService: () =>
    request<RestartResponse>("/update/restart", { method: "POST" }),
};
