import { request, getAuthToken } from "../request";
import { getApiUrl } from "../config";

export type MobileSetupState =
  | "needs_device"
  | "needs_install"
  | "ready"
  | "unsupported";

export interface MobileAgentControl {
  enabled: boolean;
  device: string | null;
}

export interface MobileStatusResponse {
  ok: boolean;
  mobile_supported: boolean;
  setup_state: MobileSetupState;
  backend: string;
  platform: string;
  reason: string;
  adb_available: boolean;
  adb_path: string;
  devices: string[];
  selected_device: string | null;
  container_running: boolean;
  agent_control?: MobileAgentControl;
}

function streamMobileSse(
  path: string,
  onLog: (line: string) => void,
  onDone: (ok: boolean, error?: string) => void,
): AbortController {
  const controller = new AbortController();
  const url = getApiUrl(path);
  const token = getAuthToken();

  // ``onDone`` is the only thing that moves the caller out of its "installing"
  // phase, so it has to fire exactly once per stream - including the two ways
  // this endpoint can end without a clean terminal frame: a terminal frame
  // followed by another frame, and the body closing with no terminal frame at
  // all (``infra/mobile/setup.py`` runs ``bash`` unguarded, so a missing shell
  // or a dying subprocess truncates the body). desktop.ts/browser.ts already
  // settle after their read loop; this one returned straight into the caller.
  let settled = false;
  const settle = (ok: boolean, error?: string) => {
    if (settled) return;
    settled = true;
    onDone(ok, error);
  };

  fetch(url, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        settle(false, `HTTP ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const payload = JSON.parse(line.slice(5).trim()) as {
              log?: string;
              done?: boolean;
              error?: string;
            };
            if (payload.log) onLog(payload.log);
            if (payload.done === true) {
              settle(true);
              return;
            }
            if (payload.done === false) {
              settle(false, payload.error);
              return;
            }
          } catch {
            /* ignore */
          }
        }
      }
      settle(false, "SSE stream ended before completion");
    })
    .catch((err: unknown) => {
      if ((err as Error).name !== "AbortError") {
        settle(false, String(err));
      }
    });
  return controller;
}

export interface MobileDeviceInfo {
  device: string;
  model: string | null;
  manufacturer: string | null;
  android_version: string | null;
  sdk: number | null;
  width: number | null;
  height: number | null;
  density_dpi: number | null;
  refresh_hz: number | null;
  mem_total_mb: number | null;
  cpu_cores: number | null;
  storage_total_gb: number | null;
  storage_used_gb: number | null;
  storage_avail_gb: number | null;
}

export const mobileApi = {
  status: () =>
    request<MobileStatusResponse>("/mobile/status", { cache: "no-store" }),
  deviceInfo: (device: string) =>
    request<MobileDeviceInfo>(
      `/mobile/devices/${encodeURIComponent(device)}/info`,
      { cache: "no-store" },
    ),
  install: (
    onLog: (line: string) => void,
    onDone: (ok: boolean, error?: string) => void,
  ) => streamMobileSse("/mobile/install", onLog, onDone),
};
