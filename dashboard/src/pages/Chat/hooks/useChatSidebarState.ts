import { useCallback, useRef, useState, useSyncExternalStore } from "react";
import { beginPointerDragSession } from "../../../hooks/usePointerDragSession";

export const CHAT_SIDEBAR_KEY = "octop:chat-sidebar:open";
export const CHAT_SIDEBAR_WIDTH_KEY = "octop:chat-sidebar:width";
export const SIDEBAR_WIDTH_MIN = 200;
export const SIDEBAR_WIDTH_MAX = 360;
export const SIDEBAR_WIDTH_DEFAULT = 248;

function loadSidebarWidth(): number {
  try {
    const raw = localStorage.getItem(CHAT_SIDEBAR_WIDTH_KEY);
    if (!raw) return SIDEBAR_WIDTH_DEFAULT;
    const n = Number.parseInt(raw, 10);
    if (
      Number.isFinite(n) &&
      n >= SIDEBAR_WIDTH_MIN &&
      n <= SIDEBAR_WIDTH_MAX
    ) {
      return n;
    }
  } catch {
    /* ignore */
  }
  return SIDEBAR_WIDTH_DEFAULT;
}

let sidebarOpen = (() => {
  try {
    return localStorage.getItem(CHAT_SIDEBAR_KEY) === "true";
  } catch {
    return false;
  }
})();

const sidebarListeners = new Set<() => void>();

function setSidebarOpenGlobal(value: boolean | ((prev: boolean) => boolean)) {
  const next = typeof value === "function" ? value(sidebarOpen) : value;
  if (next === sidebarOpen) return;
  sidebarOpen = next;
  try {
    localStorage.setItem(CHAT_SIDEBAR_KEY, String(next));
  } catch {
    /* ignore */
  }
  for (const fn of sidebarListeners) {
    try {
      fn();
    } catch {
      /* ignore */
    }
  }
}

function subscribeSidebar(listener: () => void) {
  sidebarListeners.add(listener);
  return () => {
    sidebarListeners.delete(listener);
  };
}

function getSidebarSnapshot() {
  return sidebarOpen;
}

export function useChatSidebarOpen(): [
  boolean,
  (v: boolean | ((prev: boolean) => boolean)) => void,
] {
  const value = useSyncExternalStore(
    subscribeSidebar,
    getSidebarSnapshot,
    getSidebarSnapshot,
  );
  return [value, setSidebarOpenGlobal];
}

function clampSidebarWidth(n: number): number {
  return Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, n));
}

function applySidebarWidth(el: HTMLElement | null, width: number) {
  if (!el) return;
  el.style.width = `${width}px`;
  el.style.minWidth = `${width}px`;
}

/**
 * Sidebar open/width state with a drag-to-resize handle.
 *
 * During drag we write width directly to the sidebar DOM (rAF-batched) so
 * React does not re-render SessionList on every pointermove — that was the
 * main source of jank. React state + localStorage commit only on pointerup.
 */
export function useChatSidebarState(isMobile: boolean) {
  const [sidebarOpen, setSidebarOpen] = useChatSidebarOpen();
  const [sidebarWidth, setSidebarWidth] = useState(loadSidebarWidth);
  const [isSidebarResizing, setIsSidebarResizing] = useState(false);
  const sidebarWidthRef = useRef(sidebarWidth);
  sidebarWidthRef.current = sidebarWidth;
  const sidebarElRef = useRef<HTMLDivElement>(null);
  const resizeStartRef = useRef({ x: 0, width: 0 });
  const pendingWidthRef = useRef<number | null>(null);

  const handleSidebarResizeStart = useCallback(
    (e: React.PointerEvent) => {
      if (isMobile || e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      const handle = e.currentTarget as HTMLElement;
      setIsSidebarResizing(true);
      resizeStartRef.current = {
        x: e.clientX,
        width: sidebarWidthRef.current,
      };
      pendingWidthRef.current = sidebarWidthRef.current;

      beginPointerDragSession({
        pointerId: e.pointerId,
        target: handle,
        cursor: "col-resize",
        onMove: (clientX) => {
          const next = clampSidebarWidth(
            resizeStartRef.current.width + clientX - resizeStartRef.current.x,
          );
          pendingWidthRef.current = next;
          sidebarWidthRef.current = next;
          applySidebarWidth(sidebarElRef.current, next);
        },
        onEnd: () => {
          const finalWidth = pendingWidthRef.current ?? sidebarWidthRef.current;
          pendingWidthRef.current = null;
          setIsSidebarResizing(false);
          sidebarWidthRef.current = finalWidth;
          applySidebarWidth(sidebarElRef.current, finalWidth);
          setSidebarWidth(finalWidth);
          try {
            localStorage.setItem(CHAT_SIDEBAR_WIDTH_KEY, String(finalWidth));
          } catch {
            /* ignore */
          }
        },
      });
    },
    [isMobile],
  );

  return {
    sidebarOpen,
    setSidebarOpen,
    sidebarWidth,
    isSidebarResizing,
    sidebarElRef,
    handleSidebarResizeStart,
  };
}
