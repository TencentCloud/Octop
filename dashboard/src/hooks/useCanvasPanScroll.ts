import { useCallback, useEffect, useRef, useState } from "react";

interface PanScrollOptions {
  enabled?: boolean;
  /** Pixels moved before treating gesture as drag (suppresses click). */
  threshold?: number;
  getCoords: (e: { clientX: number; clientY: number }) => {
    x: number;
    y: number;
  };
  onScroll: (x: number, y: number, deltaX: number, deltaY: number) => void;
  onClick?: (x: number, y: number) => void;
  onDoubleClick?: (x: number, y: number) => void;
  /** Called after a drag-scroll ends (not a simple click). */
  onDragEnd?: () => void;
}

/**
 * Canvas pointer handlers: click, or press-drag to scroll (inverted delta).
 * Uses Pointer Events so mouse and touch share one code path.
 */
export function useCanvasPanScroll({
  enabled = true,
  threshold = 4,
  getCoords,
  onScroll,
  onClick,
  onDoubleClick,
  onDragEnd,
}: PanScrollOptions) {
  const draggingRef = useRef(false);
  const movedRef = useRef(false);
  const lastRef = useRef({ x: 0, y: 0 });
  const anchorRef = useRef({ x: 0, y: 0 });
  const rafRef = useRef<number | null>(null);
  const pendingScrollRef = useRef<{
    x: number;
    y: number;
    dx: number;
    dy: number;
  } | null>(null);
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const flushScroll = useCallback(() => {
    rafRef.current = null;
    const p = pendingScrollRef.current;
    if (!p) return;
    pendingScrollRef.current = null;
    onScroll(p.x, p.y, p.dx, p.dy);
  }, [onScroll]);

  const queueScroll = useCallback(
    (x: number, y: number, dx: number, dy: number) => {
      const prev = pendingScrollRef.current;
      pendingScrollRef.current = {
        x,
        y,
        dx: (prev?.dx ?? 0) + dx,
        dy: (prev?.dy ?? 0) + dy,
      };
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(flushScroll);
      }
    },
    [flushScroll],
  );

  useEffect(
    () => () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      if (clickTimerRef.current !== null) clearTimeout(clickTimerRef.current);
    },
    [],
  );

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if (!enabled || e.button !== 0) return;
      e.preventDefault();
      const target = e.currentTarget;
      target.setPointerCapture(e.pointerId);
      const c = getCoords(e);
      draggingRef.current = true;
      movedRef.current = false;
      lastRef.current = c;
      anchorRef.current = c;

      const onMove = (ev: PointerEvent) => {
        if (!draggingRef.current) return;
        const cur = getCoords(ev);
        const dx = cur.x - lastRef.current.x;
        const dy = cur.y - lastRef.current.y;
        if (
          Math.abs(cur.x - anchorRef.current.x) > threshold ||
          Math.abs(cur.y - anchorRef.current.y) > threshold
        ) {
          movedRef.current = true;
          setIsDragging(true);
        }
        if (dx !== 0 || dy !== 0) {
          queueScroll(cur.x, cur.y, -dx, -dy);
          lastRef.current = cur;
        }
      };

      const onUp = (ev: PointerEvent) => {
        if (!draggingRef.current) return;
        draggingRef.current = false;
        setIsDragging(false);
        target.removeEventListener("pointermove", onMove);
        target.removeEventListener("pointerup", onUp);
        target.removeEventListener("pointercancel", onUp);
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current);
          flushScroll();
        }
        if (!movedRef.current && onClick) {
          const c2 = getCoords(ev);
          if (onDoubleClick) {
            if (clickTimerRef.current !== null)
              clearTimeout(clickTimerRef.current);
            clickTimerRef.current = setTimeout(() => {
              clickTimerRef.current = null;
              onClick(c2.x, c2.y);
            }, 250);
          } else {
            onClick(c2.x, c2.y);
          }
        } else if (movedRef.current) {
          onDragEnd?.();
        }
      };

      target.addEventListener("pointermove", onMove);
      target.addEventListener("pointerup", onUp);
      target.addEventListener("pointercancel", onUp);
    },
    [
      enabled,
      threshold,
      getCoords,
      onClick,
      onDoubleClick,
      onDragEnd,
      queueScroll,
      flushScroll,
    ],
  );

  const onDoubleClickHandler = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      if (!enabled || !onDoubleClick) return;
      e.preventDefault();
      if (clickTimerRef.current !== null) {
        clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      const c = getCoords(e);
      onDoubleClick(c.x, c.y);
    },
    [enabled, getCoords, onDoubleClick],
  );

  return {
    onPointerDown,
    onDoubleClick: onDoubleClickHandler,
    isDragging,
    pointerStyle: { touchAction: "none" as const },
  };
}
