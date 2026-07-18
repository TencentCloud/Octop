import { useCallback, useRef, useState } from "react";
import { beginPointerDragSession } from "../../../hooks/usePointerDragSession";

export type PanelSizes = { rightWidth: number; bottomHeight: number };
export type PanelResizeDirection = "horizontal" | "vertical";

const MIN_SIZE = 280;

function applyPanelSize(
  el: HTMLElement | null,
  direction: PanelResizeDirection,
  size: number,
) {
  if (!el) return;
  if (direction === "horizontal") {
    el.style.width = `${size}px`;
  } else {
    el.style.height = `${size}px`;
  }
}

/**
 * Shared docked-panel resize (right width / bottom height).
 *
 * During drag we mutate the panel element's size directly (rAF-batched) so
 * React does not re-render the chat tree / iframes on every pointermove.
 * React state + persist run only on pointerup.
 *
 * Expects the resize handle's nextElementSibling to be the sized panel
 * (matches current ChatDockPanels markup).
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
  const panelElRef = useRef<HTMLElement | null>(null);
  const directionRef = useRef<PanelResizeDirection>("horizontal");
  const onPersistRef = useRef(onPersist);
  onPersistRef.current = onPersist;

  const handleResizeStart = useCallback(
    (e: React.PointerEvent, direction: PanelResizeDirection) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      const resizeHandle = e.currentTarget as HTMLElement;
      const sibling = resizeHandle.nextElementSibling;
      panelElRef.current = sibling instanceof HTMLElement ? sibling : null;
      if (panelElRef.current) {
        panelElRef.current.setAttribute("data-dock-resizing", "1");
        if (!panelElRef.current.hasAttribute("data-dock-panel")) {
          panelElRef.current.setAttribute("data-dock-panel", "");
        }
      }

      const sizes = panelSizesRef.current;
      const pos = direction === "horizontal" ? e.clientX : e.clientY;
      const size =
        direction === "horizontal" ? sizes.rightWidth : sizes.bottomHeight;
      resizeStartRef.current = { pos, size };
      pendingSizeRef.current = size;
      directionRef.current = direction;
      setIsResizing(true);

      beginPointerDragSession({
        pointerId: e.pointerId,
        target: resizeHandle,
        cursor: direction === "horizontal" ? "col-resize" : "row-resize",
        onMove: (clientX, clientY) => {
          const currentPos =
            directionRef.current === "horizontal" ? clientX : clientY;
          const delta = resizeStartRef.current.pos - currentPos;
          const newSize = Math.max(
            MIN_SIZE,
            Math.min(
              resizeStartRef.current.size + delta,
              directionRef.current === "horizontal"
                ? window.innerWidth * 0.7
                : window.innerHeight * 0.75,
            ),
          );
          pendingSizeRef.current = newSize;
          applyPanelSize(panelElRef.current, directionRef.current, newSize);
        },
        onEnd: () => {
          const dir = directionRef.current;
          const finalSize =
            pendingSizeRef.current ??
            (dir === "horizontal"
              ? panelSizesRef.current.rightWidth
              : panelSizesRef.current.bottomHeight);
          pendingSizeRef.current = null;
          if (panelElRef.current) {
            panelElRef.current.removeAttribute("data-dock-resizing");
          }
          panelElRef.current = null;
          setIsResizing(false);

          setPanelSizes((prev) => {
            const next =
              dir === "horizontal"
                ? { ...prev, rightWidth: finalSize }
                : { ...prev, bottomHeight: finalSize };
            onPersistRef.current(next);
            return next;
          });
        },
      });
    },
    [],
  );

  return { panelSizes, setPanelSizes, isResizing, handleResizeStart };
}
