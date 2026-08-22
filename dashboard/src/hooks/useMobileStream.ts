import { useCallback, useRef, useState } from "react";
import { getAuthToken } from "../api/request";
import { H264CanvasDecoder, parseVideoInit } from "../utils/h264CanvasDecoder";

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
  /** Longest JPEG edge; 0 keeps native resolution. */
  maxSide?: number;
  /** Prefer H.264 when the host encoder is known to be fast. Default JPEG. */
  codec?: "jpeg" | "h264";
}

function buildWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/api/mobile-stream/ws`;
}

export function useMobileStream() {
  const wsRef = useRef<WebSocket | null>(null);
  const decoderRef = useRef<H264CanvasDecoder>(new H264CanvasDecoder());
  const [status, setStatus] = useState<MobileStreamState>("idle");

  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    decoderRef.current.close();
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
        canvas: HTMLCanvasElement | null;
        onFrame: (base64: string, width: number, height: number) => void;
        onVideoSize?: (width: number, height: number) => void;
        onError?: (message: string) => void;
      },
    ) => {
      disconnect();
      setStatus("connecting");
      decoderRef.current.attach(callbacks.canvas);
      const ws = new WebSocket(buildWsUrl());
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: "start",
            token: getAuthToken(),
            device: opts.device,
            quality: opts.quality ?? 75,
            max_fps: opts.maxFps ?? 10,
            max_side: opts.maxSide ?? 1080,
            // JPEG first: emulator screenrecord often stalls and starves adb taps.
            codec: opts.codec ?? "jpeg",
          }),
        );
      };
      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          const bytes = new Uint8Array(ev.data);
          if (bytes.length < 2) return;
          const key = bytes[0] === 1;
          decoderRef.current.decode(bytes.subarray(1), key);
          setStatus("streaming");
          return;
        }
        try {
          const msg = JSON.parse(String(ev.data)) as {
            type?: string;
            data?: string;
            width?: number;
            height?: number;
            message?: string;
            codec?: string;
            description?: string;
          };
          if (msg.type === "video_init") {
            const init = parseVideoInit(msg);
            if (!init) return;
            try {
              decoderRef.current.configure(init);
              if (init.width > 0 && init.height > 0) {
                callbacks.onVideoSize?.(init.width, init.height);
              }
              setStatus("streaming");
            } catch (err) {
              callbacks.onError?.(
                err instanceof Error ? err.message : "H.264 decode failed",
              );
              setStatus("error");
            }
          } else if (msg.type === "frame" && msg.data) {
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
        decoderRef.current.close();
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
