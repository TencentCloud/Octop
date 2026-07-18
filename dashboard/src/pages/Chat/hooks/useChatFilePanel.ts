import { useCallback, useEffect, useRef, useState } from "react";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import { usePanelResize, type PanelSizes } from "./usePanelResize";

const PANEL_MODE_KEY = "octop:file-panel:mode";
const PANEL_SIZE_KEY = "octop:file-panel:size";

function loadPanelMode(): PanelMode {
  try {
    const saved = localStorage.getItem(PANEL_MODE_KEY);
    if (saved === "bottom" || saved === "right" || saved === "popup") {
      return saved;
    }
  } catch {
    /* ignore */
  }
  // Files open docked to the right by default (never a centered popup).
  return "right";
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

/**
 * Chat-shell state for the docked file viewer/editor panel.
 *
 * Defaults to a right-docked layout (not a centered modal) and persists the
 * chosen mode + size in localStorage.
 */
export function useChatFilePanel(isMobile: boolean) {
  const [filePanelOpen, setFilePanelOpen] = useState(false);
  const [filePanelMode, setFilePanelMode] = useState<PanelMode>(loadPanelMode);
  const userDismissedFileRef = useRef(false);
  const { panelSizes, isResizing, handleResizeStart } = usePanelResize(
    loadPanelSizes(),
    persistPanelSizes,
  );

  const handleFileClose = useCallback(() => {
    userDismissedFileRef.current = true;
    setFilePanelOpen(false);
  }, []);

  const toggleFilePanel = useCallback(() => {
    setFilePanelOpen((prev) => !prev);
    if (isMobile) {
      setFilePanelMode("bottom");
    }
  }, [isMobile]);

  const openFilePanel = useCallback(() => {
    userDismissedFileRef.current = false;
    setFilePanelOpen(true);
    if (isMobile) {
      setFilePanelMode("bottom");
    }
  }, [isMobile]);

  useEffect(() => {
    try {
      localStorage.setItem(PANEL_MODE_KEY, filePanelMode);
    } catch {
      /* ignore */
    }
  }, [filePanelMode]);

  return {
    filePanelOpen,
    setFilePanelOpen,
    filePanelMode,
    setFilePanelMode,
    panelSizes,
    isResizing,
    handleResizeStart,
    handleFileClose,
    toggleFilePanel,
    openFilePanel,
    userDismissedFileRef,
  };
}
