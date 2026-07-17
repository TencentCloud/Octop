import { useCallback, useEffect, useRef, useState } from "react";
import type { PanelMode } from "../../../components/BrowserWorkspace";

const PANEL_MODE_KEY = "octop:browser-panel:mode";
const PANEL_SIZE_KEY = "octop:browser-panel:size";

function loadPanelMode(): PanelMode {
  try {
    const saved = localStorage.getItem(PANEL_MODE_KEY);
    if (saved === "bottom" || saved === "right" || saved === "popup") {
      return saved;
    }
  } catch {
    /* ignore */
  }
  return "popup";
}

function loadPanelSizes(): { rightWidth: number; bottomHeight: number } {
  try {
    const saved = localStorage.getItem(PANEL_SIZE_KEY);
    if (saved) {
      return JSON.parse(saved) as { rightWidth: number; bottomHeight: number };
    }
  } catch {
    /* ignore */
  }
  return { rightWidth: 560, bottomHeight: 380 };
}

export function useChatBrowserPanel(isMobile: boolean) {
  const [browserPanelOpen, setBrowserPanelOpen] = useState(false);
  const [browserPanelMode, setBrowserPanelMode] =
    useState<PanelMode>(loadPanelMode);
  const userDismissedBrowserRef = useRef(false);
  const [panelSizes, setPanelSizes] = useState(loadPanelSizes);
  const [isResizing, setIsResizing] = useState(false);
  const resizeStartRef = useRef({ pos: 0, size: 0 });

  const savePanelSizes = useCallback(
    (sizes: { rightWidth: number; bottomHeight: number }) => {
      try {
        localStorage.setItem(PANEL_SIZE_KEY, JSON.stringify(sizes));
      } catch {
        /* ignore */
      }
    },
    [],
  );

  const handleResizeStart = useCallback(
    (e: React.MouseEvent, direction: "horizontal" | "vertical") => {
      e.preventDefault();
      e.stopPropagation();
      setIsResizing(true);
      const pos = direction === "horizontal" ? e.clientX : e.clientY;
      const size =
        direction === "horizontal"
          ? panelSizes.rightWidth
          : panelSizes.bottomHeight;
      resizeStartRef.current = { pos, size };

      const handleMouseMove = (ev: MouseEvent) => {
        const currentPos = direction === "horizontal" ? ev.clientX : ev.clientY;
        const delta = resizeStartRef.current.pos - currentPos;
        const newSize = Math.max(
          280,
          Math.min(
            resizeStartRef.current.size + delta,
            direction === "horizontal"
              ? window.innerWidth * 0.7
              : window.innerHeight * 0.75,
          ),
        );
        setPanelSizes((prev) =>
          direction === "horizontal"
            ? { ...prev, rightWidth: newSize }
            : { ...prev, bottomHeight: newSize },
        );
      };

      const handleMouseUp = () => {
        setIsResizing(false);
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
        document.body.style.userSelect = "";
        document.body.style.cursor = "";
        setPanelSizes((prev) => {
          savePanelSizes(prev);
          return prev;
        });
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.userSelect = "none";
      document.body.style.cursor =
        direction === "horizontal" ? "col-resize" : "row-resize";
    },
    [panelSizes, savePanelSizes],
  );

  const handleBrowserClose = useCallback(() => {
    userDismissedBrowserRef.current = true;
    setBrowserPanelOpen(false);
  }, []);

  const toggleBrowserPanel = useCallback(() => {
    setBrowserPanelOpen((prev) => !prev);
    if (isMobile) {
      setBrowserPanelMode("bottom");
    }
  }, [isMobile]);

  const openBrowserPanel = useCallback(() => {
    userDismissedBrowserRef.current = false;
    setBrowserPanelOpen(true);
    if (isMobile) {
      setBrowserPanelMode("bottom");
    }
  }, [isMobile]);

  const resetDismissOnSessionGone = useCallback(
    (browserSessionId: string | null) => {
      if (!browserSessionId) {
        userDismissedBrowserRef.current = false;
      }
    },
    [],
  );

  useEffect(() => {
    try {
      localStorage.setItem(PANEL_MODE_KEY, browserPanelMode);
    } catch {
      /* ignore */
    }
  }, [browserPanelMode]);

  return {
    browserPanelOpen,
    setBrowserPanelOpen,
    browserPanelMode,
    setBrowserPanelMode,
    panelSizes,
    isResizing,
    handleResizeStart,
    handleBrowserClose,
    toggleBrowserPanel,
    openBrowserPanel,
    userDismissedBrowserRef,
    resetDismissOnSessionGone,
  };
}
