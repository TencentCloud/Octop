import { getApiUrl } from "../config";
import { request, getAuthToken } from "../request";

export interface DesktopStatusResponse {
  ok: boolean;
  desktop_supported: boolean;
  setup_state: string;
  platform: string;
  display: string | null;
  reason: string;
  install_script: string;
  start_command: string;
  geometry: string;
  permissions_needed: string[];
  vnc_localhost_only?: boolean | null;
  active_sessions?: number;
  session_limit?: number;
  native_capture?: boolean;
}

function streamDesktopSse(
  path: string,
  onLog: (line: string) => void,
  onDone: (success: boolean) => void,
): AbortController {
  const controller = new AbortController();
  const url = getApiUrl(path);
  const token = getAuthToken();

  fetch(url, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onDone(false);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(line.slice(6)) as {
              done?: boolean;
              success?: boolean;
              log?: string;
              error?: string;
            };
            if (payload.done) {
              if (payload.log !== undefined) {
                onLog(payload.log);
              } else if (payload.error) {
                onLog(payload.error);
              }
              onDone(Boolean(payload.success));
              return;
            }
            if (payload.log !== undefined) {
              onLog(payload.log);
            }
          } catch {
            // ignore parse errors
          }
        }
      }
      onDone(false);
    })
    .catch(() => {
      if (!controller.signal.aborted) onDone(false);
    });

  return controller;
}

export const desktopApi = {
  status: () =>
    request<DesktopStatusResponse>("/desktop/status", { cache: "no-store" }),

  setGeometry: (geometry: string) =>
    request<{ ok: boolean; geometry: string; width: number; height: number }>(
      "/desktop/geometry",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ geometry }),
      },
    ),

  installDesktop: (
    onLog: (line: string) => void,
    onDone: (success: boolean) => void,
  ): AbortController => streamDesktopSse("/desktop/install", onLog, onDone),

  uninstallDesktop: (
    onLog: (line: string) => void,
    onDone: (success: boolean) => void,
  ): AbortController => streamDesktopSse("/desktop/uninstall", onLog, onDone),
};
