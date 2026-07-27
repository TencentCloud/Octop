import { type RefObject } from "react";
import { useCanvasRemotePointer } from "./useCanvasRemotePointer";

interface BrowserCanvasInteractionOptions {
  enabled: boolean;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  onEvent: (event: Record<string, unknown>) => void;
}

/** Browser screencast canvas interaction (shared pointer protocol). */
export function useBrowserCanvasInteraction({
  enabled,
  canvasRef,
  onEvent,
}: BrowserCanvasInteractionOptions) {
  return useCanvasRemotePointer({ enabled, canvasRef, onEvent });
}
