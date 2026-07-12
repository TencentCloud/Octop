import { useCallback, type RefObject } from "react";
import { getCanvasCoords } from "../utils/browserCanvas";
import { useCanvasPanScroll } from "./useCanvasPanScroll";

interface BrowserCanvasInteractionOptions {
  enabled: boolean;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  onScroll: (x: number, y: number, deltaX: number, deltaY: number) => void;
  onClick?: (x: number, y: number) => void;
  onDoubleClick?: (x: number, y: number) => void;
  onDragEnd?: () => void;
}

/**
 * Shared canvas pointer handlers for browser views (stream + HTTP screenshot).
 */
export function useBrowserCanvasInteraction({
  enabled,
  canvasRef,
  onScroll,
  onClick,
  onDoubleClick,
  onDragEnd,
}: BrowserCanvasInteractionOptions) {
  const getCoords = useCallback(
    (e: { clientX: number; clientY: number }) =>
      getCanvasCoords(canvasRef.current, e),
    [canvasRef],
  );

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!enabled) return;
      e.preventDefault();
      const coords = getCoords(e);
      onScroll(coords.x, coords.y, e.deltaX, e.deltaY);
    },
    [enabled, getCoords, onScroll],
  );

  const pan = useCanvasPanScroll({
    enabled,
    getCoords,
    onScroll,
    onClick,
    onDoubleClick,
    onDragEnd,
  });

  return {
    getCoords,
    handleWheel,
    onPointerDown: pan.onPointerDown,
    onDoubleClick: pan.onDoubleClick,
    isDragging: pan.isDragging,
    pointerStyle: pan.pointerStyle,
  };
}
