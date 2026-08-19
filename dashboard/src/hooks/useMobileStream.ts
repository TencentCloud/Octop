import { useCallback, useRef, useState } from "react";
import { getAuthToken } from "../api/request";

export type MobileStreamState =
  | "idle"
  | "connecting"
  | "streaming"
  | "stopped"
  | "error";

export interface MobileStreamOptions {
  device?: string;
  quality?: number;
  maxFps?: number;
}

function buildWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/api/mobile-stream/ws`;
}

export function useMobileStream() {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<MobileStreamState>("idle");

  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && ws.readyState < WebSocket.CLOSING) {
      try {
        ws.send(JSON.stringify({ type: "stop" }));
      } catch {
        /* ignore */
      }
      ws.close();
    }
    setStatus("stopped");
  }, []);

  const connect = useCallback(
    (
      opts: MobileStreamOptions,
      callbacks: {
        onFrame: (base64: string, width: number, height: number) => void;
        onError?: (message: string) => void;
      },
    ) => {
      disconnect();
      setStatus("connecting");
      const ws = new WebSocket(buildWsUrl());
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: "start",
            token: getAuthToken(),
            device: opts.device,
            quality: opts.quality ?? 80,
            max_fps: opts.maxFps ?? 8,
          }),
        );
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as {
            type?: string;
            data?: string;
            width?: number;
            height?: number;
            message?: string;
          };
          if (msg.type === "frame" && msg.data) {
            setStatus("streaming");
            callbacks.onFrame(msg.data, msg.width ?? 0, msg.height ?? 0);
          } else if (msg.type === "error") {
            setStatus("error");
            callbacks.onError?.(msg.message ?? "stream error");
          }
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => {
        setStatus("error");
        callbacks.onError?.("WebSocket error");
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        setStatus((s) => (s === "streaming" ? "stopped" : s));
      };
    },
    [disconnect],
  );

  const sendEvent = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }, []);

  return { status, connect, disconnect, sendEvent };
}
