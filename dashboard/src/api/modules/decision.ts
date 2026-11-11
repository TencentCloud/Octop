import i18n from "../../i18n";
import { getApiUrl } from "../config";
import { getAuthToken, request } from "../request";

export type DecisionProvider = "laya" | "jev" | "microsoft" | "custom";

export interface DecisionServiceConfig {
  provider: DecisionProvider;
  endpoint: string;
  model: string;
  api_key_set: boolean;
}

export interface DecisionSettings {
  enabled: boolean;
  provider: DecisionProvider;
  endpoint: string;
  model: string;
  services?: DecisionServiceConfig[];
  skills: boolean;
  tools: boolean;
  team: boolean;
  threshold: number;
  tool_min_count: number;
  api_key_set: boolean;
  active: boolean;
}

export interface DecisionServiceBody {
  provider: DecisionProvider;
  endpoint: string;
  model: string;
  api_key?: string | null;
}

export interface DecisionSettingsBody {
  enabled: boolean;
  provider: DecisionProvider;
  endpoint: string;
  model: string;
  services?: DecisionServiceBody[];
  skills: boolean;
  tools: boolean;
  team: boolean;
  threshold: number;
  tool_min_count: number;
  api_key?: string | null;
}

export type LayaPhase =
  | "missing"
  | "installing"
  | "starting"
  | "running"
  | "stopped"
  | "failed";

export interface LayaStatus {
  installed: boolean;
  running: boolean;
  managed: boolean;
  phase: LayaPhase;
  endpoint: string;
  port: number;
  command: string;
  logs: string[];
}

function streamLayaInstall(
  onLog: (line: string) => void,
  onDone: (success: boolean) => void,
): AbortController {
  const controller = new AbortController();
  const token = getAuthToken();
  fetch(getApiUrl("/settings/decision/laya/install"), {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Accept-Language": i18n.language?.startsWith("zh") ? "zh" : "en",
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
              if (payload.log) onLog(payload.log);
              else if (payload.error) onLog(payload.error);
              onDone(Boolean(payload.success));
              return;
            }
            if (payload.log) onLog(payload.log);
          } catch {
            // Ignore a partial frame; the next chunk completes it.
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

export const decisionApi = {
  get: () => request<DecisionSettings>("/settings/decision"),
  save: (body: DecisionSettingsBody) =>
    request<DecisionSettings>("/settings/decision", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  test: (body: {
    endpoint?: string;
    api_key?: string;
    model?: string;
    provider?: DecisionProvider;
  }) =>
    request<{ ok: boolean; probability?: number; error?: string }>(
      "/settings/decision/test",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  layaStatus: () =>
    request<LayaStatus>("/settings/decision/laya", { cache: "no-store" }),
  installLaya: (
    onLog: (line: string) => void,
    onDone: (success: boolean) => void,
  ) => streamLayaInstall(onLog, onDone),
  startLaya: () =>
    request<LayaStatus>("/settings/decision/laya/start", { method: "POST" }),
  stopLaya: () =>
    request<LayaStatus>("/settings/decision/laya/stop", { method: "POST" }),
};
