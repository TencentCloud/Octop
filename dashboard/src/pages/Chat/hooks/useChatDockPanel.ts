import { useCallback, useEffect, useRef, useState } from "react";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import {
  canonicalizeDockFilePath,
  dockFileTabId,
  isHostAbsolutePath,
  normalizeDockFilePath,
} from "../utils/dockFilePath";
import { usePanelResize, type PanelSizes } from "./usePanelResize";

const PANEL_MODE_KEY = "octop:chat-dock:mode";
const PANEL_SIZE_KEY = "octop:chat-dock:size";
/** Legacy keys — read once for migration. */
const LEGACY_FILE_MODE_KEY = "octop:file-panel:mode";
const LEGACY_BROWSER_MODE_KEY = "octop:browser-panel:mode";
const LEGACY_FILE_SIZE_KEY = "octop:file-panel:size";
const LEGACY_BROWSER_SIZE_KEY = "octop:browser-panel:size";

export type DockTab =
  | { id: "files"; kind: "files" }
  | { id: "browser"; kind: "browser" }
  | { id: "terminal"; kind: "terminal" }
  | { id: "phone"; kind: "phone" }
  | { id: string; kind: "file"; path: string };

export type DockTabId = DockTab["id"];

function loadPanelMode(): PanelMode {
  try {
    const saved = localStorage.getItem(PANEL_MODE_KEY);
    if (saved === "bottom" || saved === "right" || saved === "popup") {
      return saved;
    }
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

function ensureFilesTab(tabs: DockTab[]): DockTab[] {
  if (tabs.some((t) => t.id === "files")) return tabs;
  return [{ id: "files", kind: "files" }, ...tabs];
}

function fallbackActiveId(
  tabs: DockTab[],
  closedId: DockTabId,
  prevActive: DockTabId | null,
): DockTabId | null {
  if (tabs.length === 0) return null;
  if (prevActive !== closedId && tabs.some((t) => t.id === prevActive)) {
    return prevActive;
  }
  if (tabs.some((t) => t.id === "files")) return "files";
  return tabs[tabs.length - 1]?.id ?? null;
}

/**
 * Shared chat dock with tabbed file list / file viewers / browser / terminal / phone.
 */
export function useChatDockPanel(isMobile: boolean, agentId?: string | null) {
  const [dockOpen, setDockOpen] = useState(false);
  const [dockMode, setDockMode] = useState<PanelMode>(loadPanelMode);
  const [openTabs, setOpenTabs] = useState<DockTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<DockTabId | null>(null);
  const { panelSizes, isResizing, handleResizeStart } = usePanelResize(
    loadPanelSizes(),
    persistPanelSizes,
  );

  // File paths and browser sessions are agent-scoped. Only wipe tabs when
  // switching between two real agents (ignore null ↔ id first-paint races).
  const prevAgentIdRef = useRef(agentId);
  useEffect(() => {
    const prev = prevAgentIdRef.current;
    prevAgentIdRef.current = agentId;
    if (prev == null || agentId == null || prev === agentId) return;
    setDockOpen(false);
    setOpenTabs([]);
    setActiveTabId(null);
  }, [agentId]);

  const openDock = useCallback(() => {
    setDockOpen(true);
    if (isMobile) {
      setDockMode("bottom");
    }
  }, [isMobile]);

  const handleClose = useCallback(() => {
    setDockOpen(false);
  }, []);

  const openFileList = useCallback(() => {
    setOpenTabs((prev) => ensureFilesTab(prev));
    setActiveTabId("files");
    openDock();
  }, [openDock]);

  const openFileAt = useCallback(
    (path?: string | null) => {
      if (!path?.trim()) {
        openFileList();
        return;
      }
      const hostAbs = normalizeDockFilePath(path);
      // Keep host-absolute tool paths. Collapsing ``~/.octop/agents/<id>/…`` to a
      // relative key breaks virtual ``root_dir`` nests (bytes live under
      // ``{root}/Users/…/.octop/agents/<id>/…``, not the real agent home).
      const tabPath = isHostAbsolutePath(hostAbs)
        ? hostAbs
        : canonicalizeDockFilePath(path, agentId);
      if (!tabPath) {
        openFileList();
        return;
      }
      const id = dockFileTabId(tabPath, agentId);
      setOpenTabs((prev) => {
        if (prev.some((t) => t.id === id)) return prev;
        return [...prev, { id, kind: "file", path: tabPath }];
      });
      setActiveTabId(id);
      openDock();
    },
    [agentId, openDock, openFileList],
  );

  const openBrowserTab = useCallback(() => {
    setOpenTabs((prev) => {
      if (prev.some((t) => t.id === "browser")) return prev;
      return [...prev, { id: "browser", kind: "browser" }];
    });
    setActiveTabId("browser");
    openDock();
  }, [openDock]);

  const openTerminalTab = useCallback(() => {
    setOpenTabs((prev) => {
      if (prev.some((t) => t.id === "terminal")) return prev;
      return [...prev, { id: "terminal", kind: "terminal" }];
    });
    setActiveTabId("terminal");
    openDock();
  }, [openDock]);

  const openPhoneTab = useCallback(() => {
    setOpenTabs((prev) => {
      if (prev.some((t) => t.id === "phone")) return prev;
      return [...prev, { id: "phone", kind: "phone" }];
    });
    setActiveTabId("phone");
    openDock();
  }, [openDock]);

  /** Toggle dock open/closed around a dedicated tab (browser / terminal / phone). */
  const toggleDockTab = useCallback(
    (tab: Extract<DockTab, { kind: "browser" | "terminal" | "phone" }>) => {
      setDockOpen((prevOpen) => {
        if (prevOpen && activeTabId === tab.id) {
          return false;
        }
        setOpenTabs((prev) => {
          if (prev.some((t) => t.id === tab.id)) return prev;
          return [...prev, tab];
        });
        setActiveTabId(tab.id);
        return true;
      });
      if (isMobile) {
        setDockMode("bottom");
      }
    },
    [activeTabId, isMobile],
  );

  const toggleBrowserPanel = useCallback(() => {
    toggleDockTab({ id: "browser", kind: "browser" });
  }, [toggleDockTab]);

  const toggleTerminalPanel = useCallback(() => {
    toggleDockTab({ id: "terminal", kind: "terminal" });
  }, [toggleDockTab]);

  const togglePhonePanel = useCallback(() => {
    toggleDockTab({ id: "phone", kind: "phone" });
  }, [toggleDockTab]);

  const closeTab = useCallback((id: DockTabId) => {
    setOpenTabs((prev) => {
      const next = prev.filter((t) => t.id !== id);
      setActiveTabId((current) => {
        const nextActive = fallbackActiveId(next, id, current);
        if (next.length === 0) {
          setDockOpen(false);
        }
        return nextActive;
      });
      return next;
    });
  }, []);

  const setActiveTab = useCallback((id: DockTabId) => {
    setActiveTabId(id);
    setDockOpen(true);
  }, []);

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

  useEffect(() => {
    try {
      localStorage.setItem(PANEL_MODE_KEY, dockMode);
    } catch {
      /* ignore */
    }
  }, [dockMode]);

  const activeTab =
    openTabs.find((t) => t.id === activeTabId) ?? openTabs[0] ?? null;
  const filePath = activeTab?.kind === "file" ? activeTab.path : null;

  return {
    dockOpen,
    dockMode,
    filePath,
    openTabs,
    activeTabId,
    activeTab,
    panelSizes,
    isResizing,
    handleResizeStart,
    handleClose,
    handleModeChange,
    openFileAt,
    openFileList,
    openBrowserTab,
    toggleBrowserPanel,
    openTerminalTab,
    toggleTerminalPanel,
    openPhoneTab,
    togglePhonePanel,
    closeTab,
    setActiveTab,
  };
}
