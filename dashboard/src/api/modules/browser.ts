import { request, getAuthToken } from "../request";
import { getApiUrl, getWsUrl } from "../config";
import type {
  BrowserReplayRequest,
  BrowserReplayResponse,
  BrowserRecordReplayStatus,
  BrowserRecordStartRequest,
  BrowserRecordStartResponse,
  BrowserRecordStopRequest,
  BrowserRecordStopResponse,
  BrowserRecordStopAndGenerateSkillRequest,
  BrowserRecordStopAndGenerateSkillResponse,
  BrowserSkillContentRequest,
  BrowserSkillContentResponse,
  BrowserSession,
  BrowserSessionsResponse,
} from "../types/browser";

// -- Browser environment types --
export interface BrowserEnvStatus {
  installed: boolean;
  browser_type: "system" | "playwright" | null;
  path: string | null;
}

function streamBrowserSse(
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

// Browser API
export const browserApi = {
  // -- Environment (Setup Wizard) --

  /** Check if a usable browser is available on the host. */
  checkEnvStatus: () => request<BrowserEnvStatus>("/browser/env-status"),

  /**
   * Start Playwright Chromium installation via SSE stream (POST).
   * Uses fetch() since EventSource only supports GET.
   *
   * @param onLog  Called for each progress line
   * @param onDone Called when installation finishes
   * @returns AbortController to cancel the request
   */
  installBrowser: (
    onLog: (line: string) => void,
    onDone: (success: boolean) => void,
  ): AbortController => streamBrowserSse("/browser/install", onLog, onDone),

  /**
   * Remove Playwright-managed Chromium via SSE (admin).
   * Does not touch system Chrome/Chromium or harness profiles.
   */
  uninstallBrowser: (
    onLog: (line: string) => void,
    onDone: (success: boolean) => void,
  ): AbortController => streamBrowserSse("/browser/uninstall", onLog, onDone),

  // -- Sessions --

  getSessions: (conversationId?: string) => {
    const path = conversationId
      ? `/browser/harness-sessions?conversation_id=${encodeURIComponent(
          conversationId,
        )}`
      : "/browser/harness-sessions";
    return request<BrowserSessionsResponse>(path);
  },

  handoff: (sessionId: string, target: "agent" | "user", reason = "") =>
    request<{ ok: boolean; session: BrowserSession }>(
      `/browser/sessions/${sessionId}/handoff`,
      {
        method: "POST",
        body: JSON.stringify({ target, reason }),
      },
    ),

  // -- Browser stream (WebSocket CDP screencast, ~10 fps) --

  /**
   * Open a WebSocket connection to the browser CDP screencast stream.
   * Uses `Page.startScreencast` for high-FPS JPEG streaming.
   *
   * Server → Client messages:
   *   {type: "frame", data: "<base64 JPEG>", metadata: {...}}
   *   {type: "status", status: "browser_started|streaming|stopped|error"}
   *   {type: "tabs", tabs: [{id, url, title, active}]}
   *   {type: "error", message: "..."}
   *
   * Client → Server messages:
   *   {type: "start", reuse_session: true, width: N, height: N}
   *   {type: "stop"}
   *   {type: "click", x: N, y: N}
   *   ... (see browser.py for full WS protocol)
   */
  browserStreamWs: (width = 1280, height = 720): WebSocket => {
    const token = getAuthToken();
    const params = new URLSearchParams();
    params.set("width", String(width));
    params.set("height", String(height));
    if (token) {
      params.set("token", token);
    }
    const wsUrl = `${getWsUrl("/browser-stream/ws")}?${params.toString()}`;
    return new WebSocket(wsUrl);
  },

  // -- Tabs (REST fallback when WebSocket is unavailable) --

  /**
   * Switch the active tab by page_id.
   */
  switchTab: (sessionId: string, pageId: string) =>
    request<{ ok: boolean; page_id: string; url: string }>(
      `/browser/sessions/${sessionId}/tabs/switch`,
      {
        method: "POST",
        body: JSON.stringify({ page_id: pageId }),
      },
    ),

  /**
   * Create a new browser tab, optionally navigating to a URL.
   */
  newTab: (sessionId: string, url = "about:blank") =>
    request<{ ok: boolean; page_id: string; url: string; tabs: TabInfo[] }>(
      `/browser/sessions/${sessionId}/tabs/new`,
      {
        method: "POST",
        body: JSON.stringify({ url }),
      },
    ),

  /**
   * Close a browser tab by page_id.
   */
  closeTab: (sessionId: string, pageId: string) =>
    request<{ ok: boolean; closed: string; tabs: TabInfo[] }>(
      `/browser/sessions/${sessionId}/tabs/close`,
      {
        method: "POST",
        body: JSON.stringify({ page_id: pageId }),
      },
    ),

  // -- Browser record/replay --

  recordReplayStatus: () =>
    request<BrowserRecordReplayStatus>("/browser/record-replay/status"),

  startRecording: (payload: BrowserRecordStartRequest) =>
    request<BrowserRecordStartResponse>("/browser/record-replay/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  stopRecording: (payload: BrowserRecordStopRequest) =>
    request<BrowserRecordStopResponse>("/browser/record-replay/stop", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  replayRecording: (payload: BrowserReplayRequest) =>
    request<BrowserReplayResponse>("/browser/record-replay/replay", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // -- Stop recording + generate skill --

  stopAndGenerateSkill: (payload: BrowserRecordStopAndGenerateSkillRequest) =>
    request<BrowserRecordStopAndGenerateSkillResponse>(
      "/browser/record-replay/stop-and-generate-skill",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),

  // -- Read skill content for a recording --

  getSkillContent: (payload: BrowserSkillContentRequest) =>
    request<BrowserSkillContentResponse>(
      "/browser/record-replay/skill-content",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
};

// -- Tab info type --
export interface TabInfo {
  page_id: string;
  url: string;
  title?: string;
  active: boolean;
}
