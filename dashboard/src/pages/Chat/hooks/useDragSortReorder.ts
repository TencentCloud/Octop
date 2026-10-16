/**
 * useDragSortReorder - pointer-events drag & drop reordering for plain lists.
 *
 * No third-party DnD dependency: rows carry ``data-drag-item`` attributes, a
 * dedicated handle starts the gesture (so row clicks still work), a small
 * threshold separates clicks from drags, and the hovered row + insert side
 * are resolved from ``document.elementFromPoint`` on pointermove.
 *
 * Pointer capture keeps move/up events flowing to the handle even when the
 * pointer leaves the row; the click that follows a completed drag is
 * suppressed so rows don't accidentally activate.
 *
 * Usage:
 *   const drag = useDragSortReorder({ enabled, onReorder });
 *   row:    <div {...drag.getRowProps(id)}> … </div>
 *   handle: <span {...drag.getHandleProps(id)}>⠿</span>
 *   style:  combine draggingId / overId / placement with CSS-module classes.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type DragPlacement = "before" | "after";

export interface UseDragSortReorderOptions {
  enabled?: boolean;
  /** Fired once on drop: move fromId before/after toId. */
  onReorder: (fromId: string, toId: string, placement: DragPlacement) => void;
}

/** Minimum pointer travel (px) before a press becomes a drag. */
const DRAG_THRESHOLD = 4;

const DRAG_ITEM_ATTR = "data-drag-item";

export function useDragSortReorder({
  enabled = true,
  onReorder,
}: UseDragSortReorderOptions) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [placement, setPlacement] = useState<DragPlacement>("before");

  const startRef = useRef<{ id: string; x: number; y: number } | null>(null);
  const activeRef = useRef(false); // past threshold, actually dragging
  const suppressClickRef = useRef(false);
  const onReorderRef = useRef(onReorder);
  useEffect(() => {
    onReorderRef.current = onReorder;
  }, [onReorder]);

  const reset = useCallback(() => {
    startRef.current = null;
    activeRef.current = false;
    setDraggingId(null);
    setOverId(null);
  }, []);

  const handlePointerDown = useCallback(
    (id: string) => (e: React.PointerEvent) => {
      if (!enabled || e.button !== 0) return;
      startRef.current = { id, x: e.clientX, y: e.clientY };
      activeRef.current = false;
      // Keep receiving pointermove/up even when the pointer leaves the handle.
      (e.target as Element).setPointerCapture?.(e.pointerId);
    },
    [enabled],
  );

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const start = startRef.current;
    if (!start) return;
    const dx = e.clientX - start.x;
    const dy = e.clientY - start.y;
    if (!activeRef.current) {
      if (Math.hypot(dx, dy) < DRAG_THRESHOLD) return; // still a click
      activeRef.current = true;
      setDraggingId(start.id);
    }
    const el = document.elementFromPoint(e.clientX, e.clientY);
    const row = el?.closest?.(`[${DRAG_ITEM_ATTR}]`) as HTMLElement | null;
    const over = row?.getAttribute(DRAG_ITEM_ATTR) ?? null;
    if (!over || over === start.id) {
      setOverId(null);
      return;
    }
    const rect = row!.getBoundingClientRect();
    const next: DragPlacement =
      e.clientY < rect.top + rect.height / 2 ? "before" : "after";
    setOverId(over);
    setPlacement(next);
  }, []);

  const handlePointerUp = useCallback(() => {
    const start = startRef.current;
    const wasActive = activeRef.current;
    const over = overId;
    const side = placement;
    if (wasActive) suppressClickRef.current = true;
    reset();
    if (wasActive && start && over && over !== start.id) {
      onReorderRef.current(start.id, over, side);
    }
  }, [overId, placement, reset]);

  // A drag can end with mouseup anywhere (pointer may leave the handle);
  // pointer capture keeps events on the handle, but be defensive anyway.
  useEffect(() => {
    const onUp = () => {
      if (startRef.current) handlePointerUp();
    };
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", reset);
    return () => {
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", reset);
    };
  }, [handlePointerUp, reset]);

  // Swallow the click that follows a completed drag so rows don't activate.
  useEffect(() => {
    if (!suppressClickRef.current) return;
    const stop = (e: Event) => {
      e.stopPropagation();
      e.preventDefault();
      suppressClickRef.current = false;
    };
    window.addEventListener("click", stop, true);
    return () => window.removeEventListener("click", stop, true);
  });

  const getHandleProps = useCallback(
    (id: string) => ({
      onPointerDown: handlePointerDown(id),
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
      onClick: (e: React.MouseEvent) => e.stopPropagation(),
      "aria-label": "reorder",
      role: "button" as const,
      tabIndex: -1,
    }),
    [handlePointerDown, handlePointerMove, handlePointerUp],
  );

  const getRowProps = useCallback(
    (id: string) => ({
      [DRAG_ITEM_ATTR]: id,
    }),
    [],
  );

  return {
    draggingId,
    overId,
    placement,
    getHandleProps,
    getRowProps,
  };
}
