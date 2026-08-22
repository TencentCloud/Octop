import React, {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Spin, Tooltip } from "antd";
import {
  FilePen,
  FolderOpen,
  Globe,
  RefreshCw,
  Terminal,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import BrowserWorkspace, {
  type PanelMode,
} from "../../../components/BrowserWorkspace";
import ChatDockPanelShell from "../../../components/BrowserWorkspace/ChatDockPanelShell";
import type { DisplayEnvironment } from "../../../api/types/browser";
import { resolveBrowserProfile } from "../../../utils/browserProfile";
import type { DockTab, DockTabId } from "../hooks/useChatDockPanel";
import { dockFileBasename } from "../utils/dockFilePath";
import styles from "../index.module.less";
import ChatDockFileList from "./ChatDockFileList";
import FilePanelContent from "./FilePanelContent";

const TerminalPage = lazy(() => import("../../Control/Terminal"));

interface ChatDockPanelProps {
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
  agentId: string;
  filePaths: string[];
  openTabs: DockTab[];
  activeTabId: DockTabId | null;
  onSelectTab: (id: DockTabId) => void;
  onCloseTab: (id: DockTabId) => void;
  onOpenFile: (path: string) => void;
  browserEnvironment?: DisplayEnvironment;
  /**
   * False while the chat dock shell is closed but keep-alive mounted.
   * Mirrors Workbench ``isVisible`` so terminal does not treat hide as a
   * fresh first visit.
   */
  surfaceVisible?: boolean;
}

/**
 * Tabbed dock shell: file list + per-file viewers + browser + terminal.
 * Bodies stay mounted after first open so streams / editors survive tab switches.
 */
const ChatDockPanel: React.FC<ChatDockPanelProps> = ({
  mode,
  onModeChange,
  onClose,
  style,
  agentId,
  filePaths,
  openTabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  onOpenFile,
  browserEnvironment = "desktop",
  surfaceVisible = true,
}) => {
  const { t } = useTranslation();
  const [browserMounted, setBrowserMounted] = useState(
    openTabs.some((tab) => tab.kind === "browser"),
  );
  const [terminalMounted, setTerminalMounted] = useState(
    openTabs.some((tab) => tab.kind === "terminal"),
  );
  const [mountedFilePaths, setMountedFilePaths] = useState<string[]>(() =>
    openTabs.filter((tab) => tab.kind === "file").map((tab) => tab.path),
  );
  const [fileActionsByPath, setFileActionsByPath] = useState<
    Record<string, ReactNode>
  >({});
  const browserRefreshRef = useRef<(() => void) | null>(null);
  const fileActionsHandlersRef = useRef<
    Record<string, (actions: ReactNode | null) => void>
  >({});

  useEffect(() => {
    const hasBrowser = openTabs.some((tab) => tab.kind === "browser");
    const hasTerminal = openTabs.some((tab) => tab.kind === "terminal");
    setBrowserMounted(hasBrowser);
    setTerminalMounted(hasTerminal);
    const openFilePaths = new Set(
      openTabs.filter((tab) => tab.kind === "file").map((tab) => tab.path),
    );
    setMountedFilePaths((prev) => {
      const next = prev.filter((path) => openFilePaths.has(path));
      let changed = next.length !== prev.length;
      for (const path of openFilePaths) {
        if (!next.includes(path)) {
          next.push(path);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    setFileActionsByPath((prev) => {
      let changed = false;
      const next: Record<string, ReactNode> = {};
      for (const path of Object.keys(prev)) {
        if (openFilePaths.has(path)) {
          next[path] = prev[path];
        } else {
          changed = true;
          delete fileActionsHandlersRef.current[path];
        }
      }
      return changed ? next : prev;
    });
  }, [openTabs]);

  const handleBrowserRefreshReady = useCallback((refresh: () => void) => {
    browserRefreshRef.current = refresh;
  }, []);

  const getFileActionsHandler = useCallback((path: string) => {
    const existing = fileActionsHandlersRef.current[path];
    if (existing) return existing;
    const handler = (actions: ReactNode | null) => {
      setFileActionsByPath((prev) => {
        if (actions == null) {
          if (!(path in prev)) return prev;
          const next = { ...prev };
          delete next[path];
          return next;
        }
        if (prev[path] === actions) return prev;
        return { ...prev, [path]: actions };
      });
    };
    fileActionsHandlersRef.current[path] = handler;
    return handler;
  }, []);

  const sessionId = resolveBrowserProfile();
  const activeTab =
    openTabs.find((tab) => tab.id === activeTabId) ?? openTabs[0] ?? null;
  const terminalVisible = surfaceVisible && activeTab?.kind === "terminal";

  const tabBar = (
    <div className={styles.dockTabBar} role="tablist">
      {openTabs.map((tab) => {
        const selected = tab.id === (activeTab?.id ?? null);
        const label =
          tab.kind === "files" ? (
            <>
              <FolderOpen size={16} strokeWidth={2} aria-hidden />
              <span>{t("chat.dockFileList", "文件变更")}</span>
            </>
          ) : tab.kind === "browser" ? (
            <>
              <Globe size={16} strokeWidth={2} aria-hidden />
              <span>{t("chat.remoteBrowserTitle", "远程浏览器")}</span>
            </>
          ) : tab.kind === "terminal" ? (
            <>
              <Terminal size={16} strokeWidth={2} aria-hidden />
              <span>{t("chat.dockTerminalTitle", "终端")}</span>
            </>
          ) : (
            <>
              <FilePen size={16} strokeWidth={2} aria-hidden />
              <span title={tab.path}>{dockFileBasename(tab.path)}</span>
            </>
          );
        return (
          <div
            key={tab.id}
            className={`${styles.dockTab} ${
              selected ? styles.dockTabActive : ""
            }`}
            role="tab"
            aria-selected={selected}
          >
            <button
              type="button"
              className={styles.dockTabLabel}
              onClick={() => onSelectTab(tab.id)}
            >
              {label}
            </button>
            <button
              type="button"
              className={styles.dockTabClose}
              onClick={(e) => {
                e.stopPropagation();
                onCloseTab(tab.id);
              }}
              aria-label={t("common.close", "关闭")}
            >
              <X size={12} strokeWidth={2} />
            </button>
          </div>
        );
      })}
    </div>
  );

  const toolbarActions = useMemo(() => {
    if (activeTab?.kind === "browser") {
      return (
        <Tooltip title={t("browserWorkspace.reconnect")}>
          <button
            type="button"
            className={styles.fileModalIconBtn}
            onClick={() => browserRefreshRef.current?.()}
            aria-label={t("browserWorkspace.reconnect")}
          >
            <RefreshCw size={16} strokeWidth={2} />
          </button>
        </Tooltip>
      );
    }
    if (activeTab?.kind === "file") {
      return fileActionsByPath[activeTab.path] ?? null;
    }
    return null;
  }, [activeTab, fileActionsByPath, t]);

  return (
    <ChatDockPanelShell
      mode={mode}
      onModeChange={onModeChange}
      onClose={onClose}
      style={style}
      title={tabBar}
      toolbarActions={toolbarActions}
    >
      <div className={styles.dockTabBodies}>
        {openTabs.some((tab) => tab.kind === "files") && (
          <div
            className={styles.dockTabBody}
            hidden={activeTab?.kind !== "files"}
            style={{
              display: activeTab?.kind === "files" ? "flex" : "none",
            }}
          >
            <ChatDockFileList
              agentId={agentId}
              filePaths={filePaths}
              onOpenFile={onOpenFile}
            />
          </div>
        )}

        {mountedFilePaths.map((path) => {
          const isActive =
            activeTab?.kind === "file" && activeTab.path === path;
          return (
            <div
              key={path}
              className={styles.dockTabBody}
              hidden={!isActive}
              style={{ display: isActive ? "flex" : "none" }}
            >
              <FilePanelContent
                agentId={agentId}
                filePath={path}
                onActionsChange={getFileActionsHandler(path)}
              />
            </div>
          );
        })}

        {browserMounted && (
          <div
            className={styles.dockTabBody}
            hidden={activeTab?.kind !== "browser"}
            style={{
              display: activeTab?.kind === "browser" ? "flex" : "none",
            }}
          >
            <BrowserWorkspace
              sessionId={sessionId}
              environment={browserEnvironment}
              hideHeaderRefresh
              style={{ flex: 1, minHeight: 0 }}
              onRefreshReady={handleBrowserRefreshReady}
            />
          </div>
        )}

        {terminalMounted && (
          <div
            className={styles.dockTabBody}
            style={{ display: terminalVisible ? "flex" : "none" }}
            aria-hidden={!terminalVisible}
          >
            <Suspense
              fallback={
                <div className={styles.dockTerminalLoading}>
                  <Spin size="small" />
                </div>
              }
            >
              <TerminalPage embedded isVisible={terminalVisible} />
            </Suspense>
          </div>
        )}
      </div>
    </ChatDockPanelShell>
  );
};

export default ChatDockPanel;
