import { useCallback, useEffect, useRef, useState } from "react";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import { usePanelResize, type PanelSizes } from "./usePanelResize";

const PANEL_MODE_KEY = "octop:chat-dock:mode";
const PANEL_SIZE_KEY = "octop:chat-dock:size";
/** Legacy keys — read once for migration. */
const LEGACY_FILE_MODE_KEY = "octop:file-panel:mode";
const LEGACY_BROWSER_MODE_KEY = "octop:browser-panel:mode";
const LEGACY_FILE_SIZE_KEY = "octop:file-panel:size";
const LEGACY_BROWSER_SIZE_KEY = "octop:browser-panel:size";

export type DockKind = "file" | "browser";

function loadPanelMode(): PanelMode {
  try {
    const saved = localStorage.getItem(PANEL_MODE_KEY);
    if (saved === "bottom" || saved === "right" || saved === "popup") {
      return saved;
    }
    // Prefer the last file-panel mode, then browser, then right dock.
    for (const key of [LEGACY_FILE_MODE_KEY, LEGACY_BROWSER_MODE_KEY]) {
      const legacy = localStorage.getItem(key);
      if (legacy === "bottom" || legacy === "right" || legacy === "popup") {
        return legacy;
      }
    }
  } catch {
    /* ignore */
  }
  return "right";
}

function loadPanelSizes(): PanelSizes {
  try {
    const saved = localStorage.getItem(PANEL_SIZE_KEY);
    if (saved) {
      return JSON.parse(saved) as PanelSizes;
    }
    for (const key of [LEGACY_FILE_SIZE_KEY, LEGACY_BROWSER_SIZE_KEY]) {
      const legacy = localStorage.getItem(key);
      if (legacy) {
        return JSON.parse(legacy) as PanelSizes;
      }
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
 * One shared chat dock for file preview / file viewer / browser.
 *
 * Opening any of 「预览」「查看文件」「查看浏览器」 reuses the same shell
 * (mode + size + popup position) and only switches the body content.
 */
export function useChatDockPanel(isMobile: boolean) {
  const [dockOpen, setDockOpen] = useState(false);
  const [dockKind, setDockKind] = useState<DockKind>("file");
  const [dockMode, setDockMode] = useState<PanelMode>(loadPanelMode);
  const [filePath, setFilePath] = useState<string | null>(null);
  const userDismissedRef = useRef(false);
  const { panelSizes, isResizing, handleResizeStart } = usePanelResize(
    loadPanelSizes(),
    persistPanelSizes,
  );

  const handleClose = useCallback(() => {
    userDismissedRef.current = true;
    setDockOpen(false);
    setFilePath(null);
  }, []);

  const openFileAt = useCallback(
    (path?: string | null) => {
      userDismissedRef.current = false;
      setFilePath(path ?? null);
      setDockKind("file");
      setDockOpen(true);
      if (isMobile) {
        setDockMode("bottom");
      }
    },
    [isMobile],
  );

  const openFilePanel = useCallback(() => {
    openFileAt(null);
  }, [openFileAt]);

  const openBrowserPanel = useCallback(() => {
    userDismissedRef.current = false;
    setDockKind("browser");
    setDockOpen(true);
    if (isMobile) {
      setDockMode("bottom");
    }
  }, [isMobile]);

  const toggleBrowserPanel = useCallback(() => {
    setDockOpen((prev) => {
      if (prev && dockKind === "browser") {
        return false;
      }
      userDismissedRef.current = false;
      setDockKind("browser");
      return true;
    });
    if (isMobile) {
      setDockMode("bottom");
    }
  }, [dockKind, isMobile]);

  const handleModeChange = useCallback(
    (mode: PanelMode) => {
      if (isMobile && mode === "right") {
        setDockMode("bottom");
        return;
      }
      setDockMode(mode);
    },
    [isMobile],
  );

  const resetDismissOnSessionGone = useCallback(
    (browserSessionId: string | null) => {
      if (!browserSessionId) {
        userDismissedRef.current = false;
      }
    },
    [],
  );

  useEffect(() => {
    try {
      localStorage.setItem(PANEL_MODE_KEY, dockMode);
    } catch {
      /* ignore */
    }
  }, [dockMode]);

  return {
    dockOpen,
    dockKind,
    dockMode,
    filePath,
    panelSizes,
    isResizing,
    handleResizeStart,
    handleClose,
    handleModeChange,
    openFileAt,
    openFilePanel,
    openBrowserPanel,
    toggleBrowserPanel,
    resetDismissOnSessionGone,
    userDismissedRef,
  };
}
