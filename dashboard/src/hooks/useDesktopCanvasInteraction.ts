import {
  useCallback,
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
} from "react";
import { useCanvasRemotePointer } from "./useCanvasRemotePointer";

interface DesktopCanvasInteractionOptions {
  enabled: boolean;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  screenWidth: number;
  screenHeight: number;
  onEvent: (event: Record<string, unknown>) => void;
}

export function useDesktopCanvasInteraction({
  enabled,
  canvasRef,
  screenWidth,
  screenHeight,
  onEvent,
}: DesktopCanvasInteractionOptions) {
  const enrichPayload = useCallback(
    (_coords: { x: number; y: number }) => ({
      canvas_width: canvasRef.current?.width ?? 0,
      canvas_height: canvasRef.current?.height ?? 0,
      screen_width: screenWidth,
      screen_height: screenHeight,
    }),
    [canvasRef, screenWidth, screenHeight],
  );

  const pointer = useCanvasRemotePointer({
    enabled,
    canvasRef,
    onEvent,
    enrichPayload,
  });

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent) => {
      if (!enabled) return;
      e.preventDefault();
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        onEvent({ type: "type", text: e.key });
      } else {
        onEvent({ type: "keydown", key: e.key });
      }
    },
    [enabled, onEvent],
  );

  const onKeyUp = useCallback(
    (e: ReactKeyboardEvent) => {
      if (!enabled) return;
      e.preventDefault();
      onEvent({ type: "keyup", key: e.key });
    },
    [enabled, onEvent],
  );

  return {
    onPointerDown: pointer.onPointerDown,
    onPointerMove: pointer.onPointerMove,
    onDoubleClick: pointer.onDoubleClick,
    onContextMenu: pointer.onContextMenu,
    onWheel: pointer.onWheel,
    onKeyDown,
    onKeyUp,
    isDragging: pointer.isDragging,
    canvasProps: {
      tabIndex: 0 as const,
      style: { touchAction: "none" as const },
    },
  };
}
