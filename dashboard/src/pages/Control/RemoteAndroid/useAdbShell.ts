import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthToken } from "../../../api/request";

export type AdbShellState = "idle" | "connecting" | "connected" | "error";

function buildWsUrl(serial: string, cols: number, rows: number): string {
  const params = new URLSearchParams();
  const token = getAuthToken();
  if (token) params.set("token", token);
  params.set("serial", serial);
  params.set("cols", String(cols));
  params.set("rows", String(rows));
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${
    window.location.host
  }/api/mobile/adb/shell/ws?${params.toString()}`;
}

export function useAdbShell() {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<AdbShellState>("idle");

  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && ws.readyState < WebSocket.CLOSING) {
      ws.close();
    }
    setState("idle");
  }, []);

  const connect = useCallback(
    (
      serial: string,
      callbacks: {
        onOutput: (data: string) => void;
        onError?: (message: string) => void;
        cols?: number;
        rows?: number;
      },
    ) => {
      if (!serial) return;
      disconnect();
      setState("connecting");
      const ws = new WebSocket(
        buildWsUrl(serial, callbacks.cols ?? 120, callbacks.rows ?? 32),
      );
      wsRef.current = ws;
      ws.onopen = () => setState("connected");
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(String(ev.data)) as {
            type?: string;
            data?: string;
            message?: string;
          };
          if (msg.type === "output" && msg.data) {
            callbacks.onOutput(msg.data);
          } else if (msg.type === "error") {
            setState("error");
            callbacks.onError?.(msg.message ?? "adb shell error");
          }
        } catch {
          /* ignore */
        }
      };
      ws.onerror = () => {
        setState("error");
        callbacks.onError?.("WebSocket error");
      };
      ws.onclose = (ev) => {
        if (wsRef.current === ws) {
          wsRef.current = null;
        }
        if (ev.code !== 1000 && ev.code !== 1001 && ev.code !== 1005) {
          setState("error");
          const reason = ev.reason?.trim();
          callbacks.onError?.(
            reason
              ? `Connection closed (${ev.code}): ${reason}`
              : `Connection closed (${ev.code})`,
          );
          return;
        }
        setState((s) => (s === "connected" ? "idle" : s));
      };
    },
    [disconnect],
  );

  const sendInput = useCallback((data: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data }));
    }
  }, []);

  const sendResize = useCallback((cols: number, rows: number) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "resize", cols, rows }));
    }
  }, []);

  useEffect(() => () => disconnect(), [disconnect]);

  return { state, connect, disconnect, sendInput, sendResize };
}
