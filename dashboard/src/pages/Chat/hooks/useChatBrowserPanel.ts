import { useCallback, useEffect, useRef, useState } from "react";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import { usePanelResize, type PanelSizes } from "./usePanelResize";

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

function loadPanelSizes(): PanelSizes {
  try {
    const saved = localStorage.getItem(PANEL_SIZE_KEY);
    if (saved) {
      return JSON.parse(saved) as PanelSizes;
    }
  } catch {
    /* ignore */
  }
  return { rightWidth: 560, bottomHeight: 380 };
}

function persistPanelSizes(sizes: PanelSizes) {
  try {
    localStorage.setItem(PANEL_SIZE_KEY, JSON.stringify(sizes));
  } catch {
    /* ignore */
  }
}

export function useChatBrowserPanel(isMobile: boolean) {
  const [browserPanelOpen, setBrowserPanelOpen] = useState(false);
  const [browserPanelMode, setBrowserPanelMode] =
    useState<PanelMode>(loadPanelMode);
  const userDismissedBrowserRef = useRef(false);
  const { panelSizes, isResizing, handleResizeStart } = usePanelResize(
    loadPanelSizes(),
    persistPanelSizes,
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
