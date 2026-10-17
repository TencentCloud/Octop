import { request } from "../request";

export interface UpdateStatus {
  current_version: string;
  /** Non-null when the process was launched via `octop service start` (systemd or launchd). */
  service_mode: "systemd" | "launchd" | null;
  /** True when wkbuddy is spawned by the Wails desktop shell (or ``OCTOP_DESKTOP=1``). */
  desktop?: boolean;
}

export interface RestartResponse {
  status: "restarting";
  service_mode: string;
}

export const updateApi = {
  getUpdateStatus: () => request<UpdateStatus>("/update/status"),
  restartService: () =>
    request<RestartResponse>("/update/restart", { method: "POST" }),
};
