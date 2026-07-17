import { useCallback, useRef, useState, useSyncExternalStore } from "react";

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

function useSidebarOpen(): [
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

export function useChatSidebarState(isMobile: boolean) {
  const [sidebarOpen, setSidebarOpen] = useSidebarOpen();
  const [sidebarWidth, setSidebarWidth] = useState(loadSidebarWidth);
  const sidebarWidthRef = useRef(sidebarWidth);
  sidebarWidthRef.current = sidebarWidth;

  const handleSidebarResizeStart = useCallback(
    (e: React.MouseEvent) => {
      if (isMobile) return;
      e.preventDefault();
      const startX = e.clientX;
      const startW = sidebarWidthRef.current;

      const onMove = (ev: MouseEvent) => {
        const next = Math.min(
          SIDEBAR_WIDTH_MAX,
          Math.max(SIDEBAR_WIDTH_MIN, startW + ev.clientX - startX),
        );
        setSidebarWidth(next);
      };

      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        document.body.style.userSelect = "";
        document.body.style.cursor = "";
        try {
          localStorage.setItem(
            CHAT_SIDEBAR_WIDTH_KEY,
            String(sidebarWidthRef.current),
          );
        } catch {
          /* ignore */
        }
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
    },
    [isMobile],
  );

  return {
    sidebarOpen,
    setSidebarOpen,
    sidebarWidth,
    handleSidebarResizeStart,
  };
}
