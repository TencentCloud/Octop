import { useState, useRef, useCallback, useEffect } from "react";
import { getAuthToken } from "../api/request";
import { normalizeUrl } from "../utils/normalizeUrl";
import {
  closeBrowserTabOptimistic,
  markBrowserTabActive,
  mergeBrowserTabsStable,
} from "../utils/browserTabs";

export type BrowserStreamState =
  | "idle"
  | "connecting"
  | "browser_started"
  | "streaming"
  | "stopped"
  | "error";

export interface BrowserTab {
  id: number | string;
  url: string;
  title: string;
  active: boolean;
}

interface BrowserStreamCallbacks {
  onFrame: (base64Data: string) => void;
  onStatusChange?: (status: BrowserStreamState) => void;
  onError?: (message: string) => void;
}

interface ConnectOptions {
  /** Optional session/conversation id. When set, the backend attaches the
   *  screencast to the same harness BrowserSession the agent is using for
   *  this conversation (the agent's `browser_use` tool registers under the
   *  conversation id as the harness profile name). When unset, the backend
   *  falls back to a "default" profile — fine for the standalone page,
   *  wrong for the chat popup. */
  sessionId?: string | null;
}

function buildWsUrl(width: number, height: number): string {
  const token = getAuthToken();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const base = `${protocol}://${window.location.host}/api/browser-stream/ws`;
  const params = new URLSearchParams({
    width: String(width),
    height: String(height),
  });
  if (token) params.set("token", token);
  return `${base}?${params.toString()}`;
}

/**
 * Manages a remote browser streaming WebSocket session.
 *
 * Handles connection lifecycle, frame reception, user input forwarding,
 * and multi-tab management.
 */
/** Lightweight session info pushed by the backend on state changes. */
export interface StreamSessionInfo {
  session_id: string;
  state: string;
  control_owner: "agent" | "user";
  current_url: string;
  conversation_id: string;
  channel_source: string;
}

export function useBrowserStream() {
  const wsRef = useRef<WebSocket | null>(null);
  const callbacksRef = useRef<BrowserStreamCallbacks | null>(null);
  const statusRef = useRef<BrowserStreamState>("idle");
  const [status, setStatus] = useState<BrowserStreamState>("idle");
  const [currentUrl, setCurrentUrl] = useState("");
  const [tabs, setTabs] = useState<BrowserTab[]>([]);
  const [sessionInfo, setSessionInfo] = useState<StreamSessionInfo | null>(
    null,
  );

  const updateStatus = useCallback((s: BrowserStreamState) => {
    statusRef.current = s;
    setStatus(s);
    callbacksRef.current?.onStatusChange?.(s);
  }, []);

  /** Connect WebSocket and start the browser. */
  const connect = useCallback(
    (
      url: string,
      width: number,
      height: number,
      callbacks: BrowserStreamCallbacks,
      options: ConnectOptions = {},
    ) => {
      callbacksRef.current = callbacks;
      updateStatus("connecting");

      // Close any existing connection
      if (wsRef.current && wsRef.current.readyState < WebSocket.CLOSING) {
        wsRef.current.close();
      }

      const wsUrl = buildWsUrl(width, height);
      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl);
      } catch (err) {
        console.error("[BrowserStream] Failed to create WebSocket:", err);
        updateStatus("error");
        return;
      }

      ws.onopen = () => {
        const startMsg: Record<string, unknown> = {
          type: "start",
          url,
          width,
          height,
          reuse_session: true,
        };
        if (options.sessionId) {
          startMsg.session_id = options.sessionId;
        } else {
          startMsg.session_id = "default";
        }
        ws.send(JSON.stringify(startMsg));
        setCurrentUrl(url);
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string) as {
            type: string;
            data?: string;
            status?: string;
            message?: string;
            tabs?: BrowserTab[];
          };

          if (msg.type === "frame" && msg.data) {
            callbacksRef.current?.onFrame(msg.data);
          } else if (msg.type === "status" && msg.status) {
            updateStatus(msg.status as BrowserStreamState);
          } else if (msg.type === "tabs" && msg.tabs) {
            setTabs((prevTabs) =>
              mergeBrowserTabsStable(prevTabs, msg.tabs ?? []),
            );
            const activeTab = msg.tabs.find((t) => t.active);
            if (activeTab) setCurrentUrl(activeTab.url);
          } else if (msg.type === "error") {
            console.error("[BrowserStream] Server error:", msg.message);
            callbacksRef.current?.onError?.(msg.message ?? "Unknown error");
            updateStatus("error");
          } else if (msg.type === "session_update") {
            // Real-time session state pushed by the backend
            const info: StreamSessionInfo = {
              session_id:
                ((msg as Record<string, unknown>).session_id as string) ?? "",
              state: ((msg as Record<string, unknown>).state as string) ?? "",
              control_owner:
                ((msg as Record<string, unknown>).control_owner as
                  | "agent"
                  | "user") ?? "agent",
              current_url:
                ((msg as Record<string, unknown>).current_url as string) ?? "",
              conversation_id:
                ((msg as Record<string, unknown>).conversation_id as string) ??
                "",
              channel_source:
                ((msg as Record<string, unknown>).channel_source as string) ??
                "dashboard",
            };
            setSessionInfo(info);
          }
        } catch {
          // Non-JSON frames — ignore
        }
      };

      ws.onerror = () => {
        updateStatus("error");
      };

      ws.onclose = () => {
        if (
          statusRef.current !== "stopped" &&
          statusRef.current !== "idle" &&
          statusRef.current !== "error"
        ) {
          updateStatus("stopped");
        }
        // Don't clear tabs on close — this preserves the tab bar state
        // during auto-reconnect so it doesn't flash empty.
      };

      wsRef.current = ws;
    },
    [updateStatus],
  );

  /** Send a user input event to the remote browser. */
  const sendEvent = useCallback((event: Record<string, unknown>): boolean => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false;
    wsRef.current.send(JSON.stringify(event));
    return true;
  }, []);

  /** Navigate to a new URL. */
  const navigate = useCallback(
    (url: string) => {
      const target = normalizeUrl(url);
      if (!target) return;
      sendEvent({ type: "navigate", url: target });
      setCurrentUrl(target);
    },
    [sendEvent],
  );

  /** Switch to a tab by id. */
  const switchTab = useCallback(
    (tabId: number | string) => {
      if (sendEvent({ type: "tab_switch", tab_id: tabId })) {
        setTabs((prevTabs) => markBrowserTabActive(prevTabs, tabId));
      }
    },
    [sendEvent],
  );

  /** Close a tab by id. */
  const closeTab = useCallback(
    (tabId: number | string) => {
      if (sendEvent({ type: "tab_close", tab_id: tabId })) {
        setTabs((prevTabs) => closeBrowserTabOptimistic(prevTabs, tabId));
      }
    },
    [sendEvent],
  );

  /** Open a new blank tab. */
  const newTab = useCallback(() => {
    sendEvent({ type: "tab_new" });
  }, [sendEvent]);

  /** Stop the remote browser. */
  const stop = useCallback(() => {
    sendEvent({ type: "stop" });
    updateStatus("stopped");
  }, [sendEvent, updateStatus]);

  /** Disconnect WebSocket completely. */
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    }
    updateStatus("idle");
    setTabs([]);
  }, [updateStatus]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  return {
    status,
    currentUrl,
    tabs,
    sessionInfo,
    connect,
    sendEvent,
    navigate,
    switchTab,
    closeTab,
    newTab,
    stop,
    disconnect,
  };
}
