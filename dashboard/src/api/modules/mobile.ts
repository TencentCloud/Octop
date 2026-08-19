import { request } from "../request";

export type MobileSetupState =
  | "needs_device"
  | "needs_install"
  | "ready"
  | "unsupported";

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
}

function streamMobileSse(
  path: string,
  onLog: (line: string) => void,
  onDone: (ok: boolean, error?: string) => void,
): AbortController {
  const controller = new AbortController();
  const token = localStorage.getItem("octop_token") ?? "";
  fetch(`/api${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        onDone(false, `HTTP ${res.status}`);
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
            if (payload.done === true) onDone(true);
            if (payload.done === false) onDone(false, payload.error);
          } catch {
            /* ignore */
          }
        }
      }
    })
    .catch((err: unknown) => {
      if ((err as Error).name !== "AbortError") {
        onDone(false, String(err));
      }
    });
  return controller;
}

export const mobileApi = {
  status: () =>
    request<MobileStatusResponse>("/mobile/status", { cache: "no-store" }),
  install: (
    onLog: (line: string) => void,
    onDone: (ok: boolean, error?: string) => void,
  ) => streamMobileSse("/mobile/install", onLog, onDone),
};
