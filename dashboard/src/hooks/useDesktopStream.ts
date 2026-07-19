import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken } from "../api/request";

export type DesktopStreamState =
  | "idle"
  | "connecting"
  | "reconnecting"
  | "streaming"
  | "stopped"
  | "error";

export interface DesktopStreamOptions {
  monitor?: number;
  quality?: number;
  maxFps?: number;
}

export interface DesktopStreamError {
  code?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface DesktopActionResult {
  action: string;
  ok: boolean;
}

interface DesktopStreamCallbacks {
  onFrame: (base64Data: string, width: number, height: number) => void;
  onStatusChange?: (status: DesktopStreamState) => void;
  onError?: (error: DesktopStreamError) => void;
  onActionResult?: (result: DesktopActionResult) => void;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_BASE_MS = 1000;

function buildWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/api/desktop-stream/ws`;
}

function closeSocket(ws: WebSocket): Promise<void> {
  if (ws.readyState >= WebSocket.CLOSING) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const finish = () => {
      ws.removeEventListener("close", finish);
      resolve();
    };
    ws.addEventListener("close", finish);
    ws.close();
    window.setTimeout(finish, 3000);
  });
}

export function useDesktopStream() {
  const wsRef = useRef<WebSocket | null>(null);
  const callbacksRef = useRef<DesktopStreamCallbacks | null>(null);
  const optionsRef = useRef<DesktopStreamOptions>({ quality: 80, maxFps: 10 });
  const statusRef = useRef<DesktopStreamState>("idle");
  const connectGenRef = useRef(0);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualStopRef = useRef(false);
  const [status, setStatus] = useState<DesktopStreamState>("idle");

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const updateStatus = useCallback((s: DesktopStreamState) => {
    statusRef.current = s;
    setStatus(s);
    callbacksRef.current?.onStatusChange?.(s);
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (manualStopRef.current || !callbacksRef.current) return;
    if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
      updateStatus("error");
      return;
    }
    const attempt = reconnectAttemptsRef.current;
    reconnectAttemptsRef.current += 1;
    updateStatus("reconnecting");
    clearReconnectTimer();
    reconnectTimerRef.current = setTimeout(
      () => {
        reconnectTimerRef.current = null;
        openConnectionRef.current(true);
      },
      RECONNECT_BASE_MS * 2 ** attempt,
    );
  }, [clearReconnectTimer, updateStatus]);

  const openConnectionRef = useRef<(isReconnect: boolean) => void>(() => {});

  const openConnection = useCallback(
    (isReconnect: boolean) => {
      if (!isReconnect) {
        manualStopRef.current = false;
        reconnectAttemptsRef.current = 0;
        clearReconnectTimer();
      }
      updateStatus(isReconnect ? "reconnecting" : "connecting");

      const gen = ++connectGenRef.current;
      const opts = optionsRef.current;

      void (async () => {
        const prev = wsRef.current;
        if (prev) {
          await closeSocket(prev);
          if (gen !== connectGenRef.current) return;
        }

        const ws = new WebSocket(buildWsUrl());
        wsRef.current = ws;

        ws.onopen = () => {
          if (gen !== connectGenRef.current) return;
          ws.send(
            JSON.stringify({
              type: "start",
              token: getAuthToken(),
              monitor: opts.monitor ?? 0,
              quality: opts.quality ?? 80,
              max_fps: opts.maxFps ?? 10,
            }),
          );
        };

        ws.onmessage = (ev) => {
          if (gen !== connectGenRef.current) return;
          try {
            const msg = JSON.parse(ev.data as string) as {
              type: string;
              data?: string;
              message?: string;
              code?: string;
              details?: Record<string, unknown>;
              width?: number;
              height?: number;
              action?: string;
              ok?: boolean;
            };
            if (msg.type === "frame" && msg.data) {
              reconnectAttemptsRef.current = 0;
              callbacksRef.current?.onFrame(
                msg.data,
                msg.width ?? 0,
                msg.height ?? 0,
              );
              if (statusRef.current !== "streaming") {
                updateStatus("streaming");
              }
            } else if (msg.type === "action_result" && msg.action) {
              callbacksRef.current?.onActionResult?.({
                action: msg.action,
                ok: Boolean(msg.ok),
              });
            } else if (msg.type === "error") {
              const err = {
                code: msg.code,
                message: msg.message ?? "Unknown error",
                details: msg.details,
              };
              if (reconnectAttemptsRef.current + 1 >= MAX_RECONNECT_ATTEMPTS) {
                callbacksRef.current?.onError?.(err);
                updateStatus("error");
              } else {
                scheduleReconnect();
              }
            }
          } catch {
            // ignore
          }
        };

        ws.onerror = () => {
          if (gen !== connectGenRef.current) return;
          if (reconnectAttemptsRef.current + 1 >= MAX_RECONNECT_ATTEMPTS) {
            updateStatus("error");
          } else {
            scheduleReconnect();
          }
        };

        ws.onclose = () => {
          if (gen !== connectGenRef.current) return;
          if (manualStopRef.current) return;
          if (statusRef.current === "error") return;
          if (statusRef.current !== "stopped" && statusRef.current !== "idle") {
            updateStatus("stopped");
            scheduleReconnect();
          }
        };
      })();
    },
    [clearReconnectTimer, scheduleReconnect, updateStatus],
  );

  openConnectionRef.current = openConnection;

  const connect = useCallback(
    (callbacks: DesktopStreamCallbacks, options: DesktopStreamOptions = {}) => {
      callbacksRef.current = callbacks;
      optionsRef.current = {
        monitor: options.monitor ?? optionsRef.current.monitor ?? 0,
        quality: options.quality ?? optionsRef.current.quality ?? 80,
        maxFps: options.maxFps ?? optionsRef.current.maxFps ?? 10,
      };
      openConnection(false);
    },
    [openConnection],
  );

  const reconnect = useCallback(() => {
    if (!callbacksRef.current) return;
    manualStopRef.current = false;
    reconnectAttemptsRef.current = 0;
    openConnection(false);
  }, [openConnection]);

  const sendEvent = useCallback((event: Record<string, unknown>): boolean => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false;
    wsRef.current.send(JSON.stringify(event));
    return true;
  }, []);

  const stop = useCallback(() => {
    manualStopRef.current = true;
    clearReconnectTimer();
    sendEvent({ type: "stop" });
    updateStatus("stopped");
  }, [clearReconnectTimer, sendEvent, updateStatus]);

  const disconnect = useCallback(() => {
    manualStopRef.current = true;
    clearReconnectTimer();
    connectGenRef.current += 1;
    const ws = wsRef.current;
    wsRef.current = null;
    ws?.close();
    updateStatus("idle");
  }, [clearReconnectTimer, updateStatus]);

  useEffect(
    () => () => {
      manualStopRef.current = true;
      clearReconnectTimer();
      connectGenRef.current += 1;
      wsRef.current?.close();
    },
    [clearReconnectTimer],
  );

  return { status, connect, reconnect, sendEvent, stop, disconnect };
}
