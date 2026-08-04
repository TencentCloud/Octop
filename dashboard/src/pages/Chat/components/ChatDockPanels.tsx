import type { PanelMode } from "../../../components/BrowserWorkspace";
import type { DisplayEnvironment } from "../../../api/types/browser";
import type { DockTab, DockTabId } from "../hooks/useChatDockPanel";
import styles from "../index.module.less";
import ChatDockPanel from "./ChatDockPanel";

interface ChatDockPanelsProps {
  isMobile: boolean;
  dockOpen: boolean;
  dockMode: PanelMode;
  isResizing: boolean;
  panelSizes: { rightWidth: number; bottomHeight: number };
  agentId: string;
  filePaths: string[];
  openTabs: DockTab[];
  activeTabId: DockTabId | null;
  onSelectTab: (id: DockTabId) => void;
  onCloseTab: (id: DockTabId) => void;
  onOpenFile: (path: string) => void;
  browserEnvironment: DisplayEnvironment;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  onResizeStart: (
    e: React.PointerEvent,
    direction: "horizontal" | "vertical",
  ) => void;
}

/**
 * Single chat dock host (file list / files / browser / terminal).
 *
 * One React tree for all layout modes so switching bottom ↔ right ↔ popup
 * does not remount TerminalPage / BrowserWorkspace. Placement is CSS/flex on
 * the chat page; popup geometry stays inside ChatDockPanelShell.
 *
 * Like Workbench keep-alive: once tabs exist, the panel stays mounted while
 * the dock is closed (display:none) so sessions are reused.
 */
export default function ChatDockPanels({
  isMobile,
  dockOpen,
  dockMode,
  isResizing,
  panelSizes,
  agentId,
  filePaths,
  openTabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  onOpenFile,
  browserEnvironment,
  onModeChange,
  onClose,
  onResizeStart,
}: ChatDockPanelsProps) {
  const keepAlive = openTabs.length > 0;
  const visible = dockOpen && keepAlive;

  if (!keepAlive) {
    return null;
  }

  const effectiveMode: PanelMode =
    dockMode === "right" && isMobile ? "popup" : dockMode;

  const panel = (
    <ChatDockPanel
      mode={effectiveMode}
      onModeChange={onModeChange}
      onClose={onClose}
      style={
        effectiveMode === "bottom"
          ? { height: panelSizes.bottomHeight }
          : effectiveMode === "right"
          ? { width: panelSizes.rightWidth }
          : undefined
      }
      agentId={agentId}
      filePaths={filePaths}
      openTabs={openTabs}
      activeTabId={activeTabId}
      onSelectTab={onSelectTab}
      onCloseTab={onCloseTab}
      onOpenFile={onOpenFile}
      browserEnvironment={browserEnvironment}
      surfaceVisible={visible}
    />
  );

  const showBottomResizer = visible && effectiveMode === "bottom";
  const showSideResizer = visible && effectiveMode === "right" && !isMobile;

  return (
    <>
      {showBottomResizer && (
        <div
          className={`${styles.panelResizer} ${styles.vertical} ${
            isResizing ? styles.resizerActive : ""
          }`}
          onPointerDown={(e) => onResizeStart(e, "vertical")}
        >
          <div className={styles.resizerHandle} />
        </div>
      )}

      {showSideResizer && (
        <div
          className={`${styles.panelResizer} ${styles.horizontal} ${
            isResizing ? styles.resizerActive : ""
          }`}
          onPointerDown={(e) => onResizeStart(e, "horizontal")}
        >
          <div className={styles.resizerHandle} />
        </div>
      )}

      <div
        // ``contents`` keeps flex/layout identical to a direct child when open;
        // ``none`` hides without unmounting (Workbench-style keep-alive).
        style={{ display: visible ? "contents" : "none" }}
        aria-hidden={!visible}
      >
        {panel}
      </div>
    </>
  );
}
