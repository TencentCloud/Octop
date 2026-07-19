import { useCallback, useEffect, useRef, useState } from "react";
import { beginPointerDragSession } from "./usePointerDragSession";

interface UseHorizontalResizeOptions {
  min: number;
  max: number;
  defaultSize: number;
  storageKey?: string;
}

function loadSize(key: string | undefined, fallback: number): number {
  if (!key) return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) ? n : fallback;
  } catch {
    return fallback;
  }
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

/**
 * Drag-to-resize a left panel width (pixels).
 *
 * During drag, width is written to the tree pane via rAF — React state commits
 * only on pointerup so tree/Monaco panels stay smooth.
 */
export function useHorizontalResize({
  min,
  max,
  defaultSize,
  storageKey,
}: UseHorizontalResizeOptions) {
  const [size, setSize] = useState(() => loadSize(storageKey, defaultSize));
  const [isResizing, setIsResizing] = useState(false);
  const sizeRef = useRef(size);
  sizeRef.current = size;
  const targetRef = useRef<HTMLElement | null>(null);
  const pendingRef = useRef<number | null>(null);
  const startRef = useRef({ x: 0, w: 0 });

  const onResizeStart = useCallback(
    (e: React.PointerEvent | React.MouseEvent) => {
      if ("button" in e && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      const handle = e.currentTarget as HTMLElement;

      // Prefer previous sibling (tree pane); fall back to parent of divider.
      const prev = handle.previousElementSibling;
      const parent = handle.parentElement;
      const treeCandidate =
        prev instanceof HTMLElement
          ? prev
          : parent?.previousElementSibling instanceof HTMLElement
          ? parent.previousElementSibling
          : null;
      // WorkspaceDrawer: resizeHandle is inside splitDivider; tree is
      // splitDivider.previousElementSibling.
      const divider =
        handle.closest("[data-split-divider]") ?? handle.parentElement;
      const fromDivider =
        divider?.previousElementSibling instanceof HTMLElement
          ? divider.previousElementSibling
          : null;
      targetRef.current = fromDivider ?? treeCandidate;

      startRef.current = { x: e.clientX, w: sizeRef.current };
      pendingRef.current = sizeRef.current;
      setIsResizing(true);
      if (targetRef.current) {
        targetRef.current.style.width = `${sizeRef.current}px`;
      }

      // MouseEvent path (no pointerId) — keep a minimal document listener.
      if (!("pointerId" in e)) {
        const onMove = (ev: MouseEvent) => {
          const next = clamp(
            startRef.current.w + ev.clientX - startRef.current.x,
            min,
            max,
          );
          pendingRef.current = next;
          if (targetRef.current) {
            targetRef.current.style.width = `${next}px`;
          }
        };
        const onUp = () => {
          const finalSize = pendingRef.current ?? sizeRef.current;
          pendingRef.current = null;
          targetRef.current = null;
          setIsResizing(false);
          sizeRef.current = finalSize;
          setSize(finalSize);
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          document.body.style.cursor = "";
          document.body.style.userSelect = "";
          if (storageKey) {
            try {
              localStorage.setItem(storageKey, String(finalSize));
            } catch {
              /* ignore */
            }
          }
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        return;
      }

      beginPointerDragSession({
        pointerId: e.pointerId,
        target: handle,
        cursor: "col-resize",
        onMove: (clientX) => {
          const next = clamp(
            startRef.current.w + clientX - startRef.current.x,
            min,
            max,
          );
          pendingRef.current = next;
          if (targetRef.current) {
            targetRef.current.style.width = `${next}px`;
          }
        },
        onEnd: () => {
          const finalSize = pendingRef.current ?? sizeRef.current;
          pendingRef.current = null;
          targetRef.current = null;
          setIsResizing(false);
          sizeRef.current = finalSize;
          setSize(finalSize);
          if (storageKey) {
            try {
              localStorage.setItem(storageKey, String(finalSize));
            } catch {
              /* ignore */
            }
          }
        },
      });
    },
    [min, max, storageKey],
  );

  useEffect(() => {
    const clamped = clamp(size, min, max);
    if (clamped !== size) setSize(clamped);
  }, [min, max, size]);

  return { size, isResizing, onResizeStart };
}
