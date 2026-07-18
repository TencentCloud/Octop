import { useCallback, useRef, useState } from "react";

export type PanelSizes = { rightWidth: number; bottomHeight: number };
export type PanelResizeDirection = "horizontal" | "vertical";

const MIN_SIZE = 280;

/**
 * Shared docked-panel resize (right width / bottom height) with pointer
 * capture + rAF throttling so drag stays smooth even over iframes.
 */
export function usePanelResize(
  initialSizes: PanelSizes,
  onPersist: (sizes: PanelSizes) => void,
) {
  const [panelSizes, setPanelSizes] = useState(initialSizes);
  const [isResizing, setIsResizing] = useState(false);
  const panelSizesRef = useRef(panelSizes);
  panelSizesRef.current = panelSizes;
  const resizeStartRef = useRef({ pos: 0, size: 0 });
  const pendingSizeRef = useRef<number | null>(null);
  const resizeFrameRef = useRef<number | null>(null);
  const onPersistRef = useRef(onPersist);
  onPersistRef.current = onPersist;

  const handleResizeStart = useCallback(
    (e: React.PointerEvent, direction: PanelResizeDirection) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const resizeHandle = e.currentTarget;
      resizeHandle.setPointerCapture(e.pointerId);
      setIsResizing(true);
      const sizes = panelSizesRef.current;
      const pos = direction === "horizontal" ? e.clientX : e.clientY;
      const size =
        direction === "horizontal" ? sizes.rightWidth : sizes.bottomHeight;
      resizeStartRef.current = { pos, size };

      const handlePointerMove = (ev: PointerEvent) => {
        const currentPos = direction === "horizontal" ? ev.clientX : ev.clientY;
        const delta = resizeStartRef.current.pos - currentPos;
        pendingSizeRef.current = Math.max(
          MIN_SIZE,
          Math.min(
            resizeStartRef.current.size + delta,
            direction === "horizontal"
              ? window.innerWidth * 0.7
              : window.innerHeight * 0.75,
          ),
        );
        if (resizeFrameRef.current !== null) return;
        resizeFrameRef.current = requestAnimationFrame(() => {
          resizeFrameRef.current = null;
          const newSize = pendingSizeRef.current;
          if (newSize === null) return;
          setPanelSizes((prev) =>
            direction === "horizontal"
              ? { ...prev, rightWidth: newSize }
              : { ...prev, bottomHeight: newSize },
          );
        });
      };

      const handlePointerUp = () => {
        if (resizeFrameRef.current !== null) {
          cancelAnimationFrame(resizeFrameRef.current);
          resizeFrameRef.current = null;
        }
        const finalSize = pendingSizeRef.current;
        pendingSizeRef.current = null;
        setIsResizing(false);
        resizeHandle.removeEventListener("pointermove", handlePointerMove);
        resizeHandle.removeEventListener("pointerup", handlePointerUp);
        resizeHandle.removeEventListener("pointercancel", handlePointerUp);
        document.body.style.userSelect = "";
        document.body.style.cursor = "";
        setPanelSizes((prev) => {
          const next =
            finalSize === null
              ? prev
              : direction === "horizontal"
              ? { ...prev, rightWidth: finalSize }
              : { ...prev, bottomHeight: finalSize };
          onPersistRef.current(next);
          return next;
        });
      };

      resizeHandle.addEventListener("pointermove", handlePointerMove);
      resizeHandle.addEventListener("pointerup", handlePointerUp);
      resizeHandle.addEventListener("pointercancel", handlePointerUp);
      document.body.style.userSelect = "none";
      document.body.style.cursor =
        direction === "horizontal" ? "col-resize" : "row-resize";
    },
    [],
  );

  return { panelSizes, setPanelSizes, isResizing, handleResizeStart };
}
